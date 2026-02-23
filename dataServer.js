/* eslint-disable radix */
/* eslint-disable no-case-declarations */
import net from 'net';
import { EventEmitter } from 'events';
import fs from 'fs';
import moment from 'moment';
import {
  Server,
  getAIS140packet,
} from '../../Modules/protocol-data-server-master';
import { dataServerActions } from '../../shared/actions';
import {
  checkComPort,
  getparamCFG,
  sendSerialCommand,
  callWriteConfiguration,
  fromMasterToCore,
} from './serialInterface';
import { log } from './logger';
import tags from '../terminalTags';
import CommandList from './sms/cmdlist';
import { CheckParameters } from './modem';
import { logDataToFile } from './autoTest';
import { handleTimeoutParameter, remakeArgs, setTimer } from './utility';

import { mainCertificatesDirectoryPath } from './constants';
import spec118Encoding from './functionalities/spec118_beltrans';
import { detailedCompare } from '../automaticTests/comparator';

export const emitter = {
  main: new EventEmitter(),
  duplicate: new EventEmitter(),
  third: new EventEmitter(),
};

let store;
const server = { main: null, duplicate: null, third: null };
let timestampStart;
let timestampEnd;

// TODO this function is required only during actions refactoring (TypeScript, unit tests, etc.)
// so that ejected functions can access their dependencies, like store, and other internals.
// this functionality should be replaced with a better mechanism when refactoring is finished.
export function exportServer() {
  return server;
}

export function exportEmitter() {
  return emitter;
}

export function exportStore() {
  return store;
}

export async function initDataServer(reduxStore) {
  store = reduxStore;
  createDataServer({ serverType: 'main' });
}

function getClientID(serverType, imei) {
  return server[serverType].clients.findIndex(
    (x) => Number(x.info.imei) === Number(imei)
  );
}

async function buildParameters(args) {
  const { serverType = 'duplicate' } = args;
  if (serverType === 'main') {
    return {
      openPort: store.getState().settings.ports,
      general: { imei: store.getState().settings.mainParameters.imei },
    };
  }

  const {
    listener,
    dataAutoReplay,
    imeiAutoReplay,
    answerToImei,
    alwaysCollectRecords,
    beltrans,
    tls,
    imeiResponseDelay,
    recordResponseDelay,
  } = args;
  const portValue = store.getState().settings.ports[serverType];
  let key;
  let cert;

  closeDuplicateServer({ serverType });

  if (tls && tls.enabled) {
    try {
      const keyPath = await fromMasterToCore(
        mainCertificatesDirectoryPath,
        tls.key
      );
      const certPath = await fromMasterToCore(
        mainCertificatesDirectoryPath,
        tls.cert
      );
      key = fs.readFileSync(keyPath);
      cert = fs.readFileSync(certPath);
    } catch (err) {
      return Promise.reject(
        new Error('Unable to get Certificate file(s)').message
      );
    }
  }
  const autoReply = {
    data: dataAutoReplay,
    imei: imeiAutoReplay,
    sequence: answerToImei,
    alwaysCollectRecords,
  };
  const openPort = {
    tcp: null,
    udp: null,
    fota: null,
    [listener]: portValue,
  };
  const general = {
    autoReply,
    beltrans,
    imeiDelay: handleTimeoutParameter(imeiResponseDelay),
    recordDelay: handleTimeoutParameter(recordResponseDelay),
    tls: { ...tls, key, cert },
  };
  return { openPort, general };
}

/**
 * Create data server
 */
export async function createDataServer(args = {}) {
  log.info({ message: 'start of createDataServer()', tag: tags.server });
  const { serverType = 'duplicate', password } = args;
  const serverTitle = serverType.charAt(0).toUpperCase() + serverType.slice(1);
  const { general, openPort } = await buildParameters(args);

  server[serverType] = new Server({
    general,
    tcp: {
      enabled: true,
      port: Number(openPort.tcp),
    },
    udp: {
      enabled: true,
      port: Number(openPort.udp),
      idleTmo: Number(30 * 1000),
    },
    fota: {
      enabled: true,
      port: Number(openPort.fota),
    },
  });

  server[serverType].on('connection', (device) => {
    log.info({
      message: `Got connection ${device.addr}:${device.port} (${serverTitle} Server)`,
      tag: tags[device.listener.toLowerCase()],
    });
    dataServerActions[serverType].clientConnected(device);
    emitter[serverType].emit('connection', device);
  });

  /**
   * TCP protocol 'authenticated' return once per connection, after IMEI acception
   * UDP protocol 'authenticated' return after every AVL (records) packet
   */
  server[serverType].on('authenticated', (device) => {
    log.info({
      message: `Got authentication ${device.addr}:${device.port} IMEI: ${device.imei} (${serverTitle} Server)`,
      tag: tags[device.listener.toLowerCase()],
    });
    dataServerActions[serverType].clientAuthenticated(device);
    emitter[serverType].emit('authenticated', device);
  });

  server[serverType].on('connection_lost', (device) => {
    log.warn({
      message: `Lost connection ${device.addr}:${device.port} IMEI: ${device.imei} (${serverTitle} Server)`,
      tag: tags[device.listener.toLowerCase()],
    });
    if (!store.getState().autoTests.testsInProgress) {
      dataServerActions[serverType].updateDataServerState({ avlRecords: {} });
    }
    dataServerActions[serverType].clientDisconnected(device);
    emitter[serverType].emit('connection_lost', device);
  });

  server[serverType].on('error', (device) => {
    log.error({
      message: `An error occurred ${device.addr}:${device.port} IMEI: ${device.imei}  (${serverTitle} Server)`,
      tag: tags[device.listener.toLowerCase()],
    });
  });

  server[serverType].on('data', (packet) => {
    if (
      serverType !== 'main' &&
      packet.password &&
      password !== packet.password
    ) {
      log.error({
        message: `server[${serverType}] --> Communication protection password mismatched`,
        tag: tags.server,
      });
      return closeDuplicateServer({ serverType });
    }
    logDataToFile({ data: packet, type: packet.type, serverType });
    switch (packet.type) {
      case 'raw': {
        log.info({
          message: `server[${serverType}] --> new packet arrived with raw data in it`,
          tag: tags.server,
        });
        emitter[serverType].emit('raw', packet);
        break;
      }
      case 'AIS-140': {
        log.info({ message: 'Received AIS-140 records!', tag: tags.ais_140 });
        dataServerActions[serverType].AIS140recordArrived(
          // imei
          packet.imei,
          // packet
          packet.buffer.toString(),
          // records
          packet.data,
          // info
          {
            timestamp: packet.timestamp,
            listener: packet.listener,
            data_protocol: packet.data_protocol,
          }
        );
        return emitter[serverType].emit('AIS-140', packet);
      }
      case 'avl': {
        log.info({
          message: `server[${serverType}] --> new packet arrived with avl data in it`,
          tag: tags.server,
        });
        const clientIndex = store
          .getState()
          .dataServer[serverType].clients.findIndex(
            (x) => x.imei === packet.imei
          );
        if (
          store.getState().dataServer[serverType].clients[clientIndex]
            .priority === undefined &&
          packet.data.records
        ) {
          dataServerActions[serverType].clientFirstAvlPacket(
            packet.imei,
            packet.data.records[0].priority
          );
        }
        switch (packet.data.codec_id) {
          case 0x3d: /* codec 61 */
          case 0x08:
          case 0x4b: /* codec 61 extended */
          case 0x8e: {
            log.info({
              message: `Received AVL records! (${serverTitle} Server)`,
              tag: tags.avl,
            });
            dataServerActions[serverType].avlRecordArrived(
              packet.imei,
              packet.data.records,
              { timestamp: new Date().valueOf(), listener: packet.listener }
            );
            emitter[serverType].emit('record', packet);
            break;
          }
          case 12:
          case 13:
          case 14: {
            log.info({
              message: `Received GPRS command: ${JSON.stringify(
                packet.data.response,
                null,
                1
              )} (${serverTitle} Server)`,
              tag: tags.gprs,
            });
            dataServerActions[serverType].gprsCmdArrived(
              packet.imei,
              packet.data.response
            );
            emitter[serverType].emit('GPRS', packet);
            break;
          }
          default:
            break;
        }
        break;
      }
      case 'custom': {
        log.info({
          message: `server[${serverType}] --> custom packet arrived`,
          tag: tags.server,
        });
        dataServerActions[serverType].customProtocolRecordArrived(
          packet.imei,
          packet.data,
          { timestamp: new Date().valueOf(), listener: packet.listener }
        );
        emitter[serverType].emit('custom', packet);
        break;
      }
      case 'ping': {
        log.info({
          message: `server[${serverType}] --> ping packet arrived`,
          tag: tags.server,
        });
        emitter[serverType].emit('ping', packet);
        break;
      }
      default:
        break;
    }
  });

  server[serverType].on('transform', (data) =>
    emitter[serverType].emit('transform', data)
  );

  server[serverType].on('0x31', (packet) =>
    emitter[serverType].emit('0x31', packet)
  );

  server[serverType].on('progress', (device) =>
    emitter[serverType].emit('fotaProgress', device)
  );

  server[serverType].on('fota', (res) => emitter[serverType].emit('fota', res));

  server[serverType].on('GPRS_sending', (data) =>
    emitter[serverType].emit('GPRS_sending', data)
  );

  return null;
}

/**
 * Close backup server
 */
export function closeDuplicateServer(args = {}) {
  log.info({ message: 'start of closeDuplicateServer()', tag: tags.server });
  const { serverType } = args;
  if (serverType) {
    if (!server[serverType]) return Promise.resolve(null);
    const listeners = ['tcp', 'udp', 'fota'];
    listeners.forEach((listener) => {
      if (listener !== 'udp') {
        server[serverType].instances[listener].forceClose();
      } else {
        server[serverType].instances[listener].close();
      }
    });
    server[serverType] = null;
    log.info({
      message: 'closeDuplicateServer() --> resolve(null)',
      tag: tags.server,
    });
    return Promise.resolve(null);
  }
  /* In case of resetResources() */
  if (!server.duplicate && !server.third) return Promise.resolve(null);
  if (server.duplicate) {
    const listeners = ['tcp', 'udp', 'fota'];
    listeners.forEach((listener) => {
      if (listener !== 'udp') {
        server.duplicate.instances[listener].forceClose();
      } else {
        server.duplicate.instances[listener].close();
      }
    });
    server.duplicate = null;
    log.info({
      message: 'closeDuplicateServer() --> resolve(null)',
      tag: tags.server,
    });
  }
  if (server.third) {
    const listeners = ['tcp', 'udp', 'fota'];
    listeners.forEach((listener) => {
      if (listener !== 'udp') {
        server.third.instances[listener].forceClose();
      } else {
        server.third.instances[listener].close();
      }
    });
    server.third = null;
    log.info({
      message: 'closeDuplicateServer() --> resolve(null)',
      tag: tags.server,
    });
  }
  return Promise.resolve(null);
}

export function checkRecordsPriority(args) {
  log.info({ message: 'start of checkRecordsPriority()', tag: tags.server });
  return new Promise((resolve, reject) => {
    const { imei } = store.getState().settings.mainParameters;
    const { timeout = { value: 5, units: 'min' }, serverType = 'main' } =
      args || {};
    const tmo = handleTimeoutParameter(timeout);
    const timer = setTimer(reject, tmo, () => {
      log.info({
        message: 'checkRecordsPriority() --> no record received --> reject',
        tag: tags.server,
      });
      emitter[serverType].removeListener('record', funcData);
    });

    let firstRecord = null;
    const funcData = (packet) => {
      if (
        packet.type === 'avl' &&
        (Number(packet.data.codec_id) === 8 ||
          Number(packet.data.codec_id) === 142) &&
        Number(packet.imei) === Number(imei) &&
        firstRecord === null
      ) {
        clearTimeout(timer);
        firstRecord = { priority: packet.data.records[0].priority };
        switch (firstRecord.priority) {
          case 0:
            firstRecord = { priority: 'low' };
            break;
          case 1:
            firstRecord = { priority: 'high/panic' };
            break;
          case 2:
            firstRecord = { priority: 'block' };
            break;
          default:
            firstRecord = { priority: '' };
        }
        log.info({
          message: 'checkRecordsPriority() --> got firstRecord --> resolve',
          tag: tags.server,
        });
        emitter[serverType].removeListener('record', funcData);
        return resolve(firstRecord);
      }
    };
    emitter[serverType].on('record', funcData);
  });
}

export function checkNotSend(args = {}) {
  log.info({ message: 'start of checkNotSend()', tag: tags.server });
  return new Promise((resolve, reject) => {
    const { serverType = 'main', timeout = { value: 5, units: 'min' } } = args;
    const tmo = handleTimeoutParameter(timeout);
    const { imei } = store.getState().settings.mainParameters;

    const timer = setTimeout(() => {
      emitter[serverType].removeListener('record', funcData);
      log.info({ message: 'checkNotSend() --> success', tag: tags.server });
      return resolve(null);
    }, tmo);

    const funcData = (packet) => {
      if (Number(packet.imei) === Number(imei)) {
        clearTimeout(timer);
        emitter[serverType].removeListener('record', funcData);
        log.info({
          message: 'checkNotSend() --> got record --> reject',
          tag: tags.server,
        });
        return reject(new Error('Got data').message);
      }
    };

    emitter[serverType].on('record', funcData);
  });
}

export function sendFota(args) {
  log.info({ message: 'start of sendFota()', tag: tags.server });
  return new Promise((resolve, reject) => {
    const fotaStartTime = new Date().getTime();
    const { imei } = store.getState().settings.mainParameters;
    const { serverType = 'main', duration = { value: 15, units: 'min' } } =
      args;
    const selectedDuration = handleTimeoutParameter(duration) || null;
    const endTimeout = 30 * 60 * 1000;
    const beginTimeout = 30 * 60 * 1000;
    const waitAfterDownloadTimeout = 6 * 60 * 1000;
    const dynamicEndTimeout = selectedDuration + endTimeout;
    let statusDone = false;
    let totalFileSize = 0;
    let averageSpeed = 0;

    const closeListeners = () => {
      emitter[serverType].removeListener('fotaProgress', fotaSendProgress);
      emitter[serverType].removeListener('fota', fotaErrHandler);
      emitter[serverType].removeListener('close', fotaErrHandler);
      emitter[serverType].removeListener('connection_lost', fotaErrHandler);
      emitter[serverType].removeListener('transform', takeTotalFileSize);
    };

    const endTimer = setTimer(reject, dynamicEndTimeout, () => {
      log.info({
        message: 'sendFota() --> endTimer reached!',
        tag: tags.server,
      });
      server[serverType].instances.fota.forceClose();
      closeListeners();
    });
    const beginTimer = setTimer(reject, beginTimeout, () => {
      log.info({
        message: 'sendFota() --> beginTimer reached!',
        tag: tags.server,
      });
      closeListeners();
      clearTimeout(endTimer);
    });

    function takeTotalFileSize(data) {
      totalFileSize = data.lengthTotal;
    }

    function calculateAverageDownloadSpeed() {
      try {
        const timeDifference = moment(timestampEnd).diff(
          moment(timestampStart)
        );
        const downloadTimeInSeconds = moment
          .duration(timeDifference)
          .asSeconds();
        const totalFileSizeInMb = totalFileSize * 8 * 0.000001; // B -> Mbits
        averageSpeed = (totalFileSizeInMb / downloadTimeInSeconds).toFixed(2);
        log.info({
          message: `Average download speed: ${averageSpeed} Mbit/s`,
          tag: tags.fota,
        });
      } catch (err) {
        log.error({
          message: `Error in calculateAverageDownloadSpeed() -> ${err.message}`,
          tag: tags.fota,
        });
      }
    }

    emitter[serverType].on('fota', fotaErrHandler);
    emitter[serverType].on('fotaProgress', fotaSendProgress);
    emitter[serverType].on('close', fotaErrHandler);
    emitter[serverType].on('connection_lost', fotaErrHandler);
    emitter[serverType].on('transform', takeTotalFileSize);

    function waitForStatusDone() {
      const endOfWaitingStatusDone =
        new Date().getTime() + waitAfterDownloadTimeout;
      (function cycle() {
        const currentTimestamp = new Date().getTime();
        if (currentTimestamp < endOfWaitingStatusDone && statusDone) {
          return null;
        }
        if (currentTimestamp >= endOfWaitingStatusDone && !statusDone) {
          closeListeners();
          clearTimeout(endTimer);
          server[serverType].instances.fota.forceClose();
          const err = new Error(
            `File was downloaded, but didn't finished within ${
              waitAfterDownloadTimeout / 60000
            } minutes`
          );
          log.error({ message: err.stack, tag: tags.fota });
          return reject(err.message);
        }
        setTimeout(() => cycle(), 3000);
      })();
    }

    function fotaSendProgress(device) {
      if (Number(device.imei) !== Number(imei)) {
        return null;
      }
      switch (device.status) {
        case 'in_progress': {
          clearTimeout(beginTimer);
          log.info({
            message: `[${device.imei}] FOTA progress: ${device.progress}%`,
            tag: tags.fota,
          });
          if (device.progress === 0) {
            timestampStart = Date.now();
          }
          if (device.progress === 100) {
            timestampEnd = Date.now();
            calculateAverageDownloadSpeed();
            waitForStatusDone();
          }
          break;
        }
        case 'error': {
          closeListeners();
          const err = `${device.err || 'FOTA error!'}`;
          log.error({ message: err.stack, tag: tags.fota });
          reject(err);
          break;
        }
        case 'done': {
          statusDone = true;
          closeListeners();
          clearTimeout(endTimer);

          const fotaEndTime = new Date().getTime();
          const fotaTestDuration = fotaEndTime - fotaStartTime;
          if (fotaTestDuration <= selectedDuration) {
            log.info({
              message: `[${device.imei}] FOTA done!`,
              tag: tags.fota,
            });
            resolve({
              message: `Average download speed - ${averageSpeed} Mbit/s`,
            });
          } else {
            const err = new Error(
              `Test duration took longer than expected. Duration: ${fotaTestDuration} (ms)`
            );
            log.error({ message: err.stack, tag: tags.fota });
            reject(err.message);
          }
          break;
        }
        default: {
          break;
        }
      }
    }

    function fotaErrHandler(err) {
      if (err.type === 'error') {
        closeListeners();
        const error = err.error ? new Error(err.error.message) : 'FOTA error!';
        log.error({
          message: `Error message: ${error}; Address: ${err.addr}, Port: ${err.port}, IMEI: ${err.imei}, UID: ${err.uid}`,
          tag: tags.fota,
        });
        reject(error);
      }
    }
  });
}

/**
 * Send GPRS command to device
 * @param {{ imei:string, command:string, wrongCRC:boolean }} args
 * @returns {Promise<null>}
 */
export function sendGprsCommand(args) {
  log.info({ message: 'start of sendGprsCommand()', tag: tags.server });
  const {
    serverType = 'main',
    command,
    wrongCRC = false,
    interval = 0,
    duration = 0,
    codec = 'codec12',
    imei: _imeiArg,
  } = args || {};
  const { imei: _imei } = store.getState().settings.mainParameters;
  const imei = _imeiArg || _imei;
  log.info({
    message: `sendGprsCommand() --> using IMEI:${imei}`,
    tag: tags.server,
  });
  const sendCommandInterval = handleTimeoutParameter(interval);
  const actionDuration = handleTimeoutParameter(duration);
  const sendOnce =
    !interval ||
    interval.value === null ||
    interval.value === 0 ||
    interval.value === '0';
  return new Promise((resolve, reject) => {
    checkClientStatus({ serverType, connStatus: true, timeout: 0 })
      .then(() => {
        (function cycle(sumOfInterval = 0) {
          if (sumOfInterval < actionDuration || sendOnce) {
            const timer = setTimer(
              reject,
              10 * 1000,
              () => {
                log.error({
                  message:
                    'sendGprsCommand() --> timer() --> Timeout passed, any status about sending',
                  tag: tags.server,
                });
                emitter[serverType].removeListener(
                  'GPRS_sending',
                  statusHandle
                );
              },
              'Timeout passed, any status about sending'
            );

            emitter[serverType].once('GPRS_sending', statusHandle);
            // eslint-disable-next-line no-inner-declarations
            function statusHandle(data) {
              clearTimeout(timer);
              if (data.done) {
                /* Successfully sent */
                if (sendOnce) {
                  log.info({
                    message: 'sendGprsCommand() --> resolve',
                    tag: tags.server,
                  });
                  return resolve(null);
                }
                log.info({
                  message: `sendGprsCommand() --> cycle(${
                    sumOfInterval + sendCommandInterval
                  })`,
                  tag: tags.server,
                });
                setTimeout(
                  () => cycle(sumOfInterval + sendCommandInterval),
                  sendCommandInterval
                );
                return null;
              }
              /* Unsuccessfully sent */
              const err = new Error(
                `sendGprsCommand() --> reject(err) --> err: ${data.error}`
              );
              log.error({ message: err.stack, tag: tags.server });
              return reject(new Error(data.error));
            }
            const clientId = getClientID(serverType, _imei);
            server[serverType].clients[clientId].sendCommand({
              command,
              wrongCRC,
              codec,
              imei,
            });
            return null;
          }
          /* GPRS command(s) sent successfuly */
          log.info({
            message: 'sendGprsCommand() --> resolve',
            tag: tags.server,
          });
          return resolve(null);
        })();
        return null;
      })
      .catch((err) => {
        log.error({
          message: `sendGprsCommand() --> reject(err) --> err: "${err}"`,
          tag: tags.server,
        });
        return reject(new Error('Error occurred').message);
      });
  });
}

/**
 * @description read GPRS commands response and check values of parameters
 * @param {{ serverType: string, imei:string, timeout:{ value:number, units:string }, command:string }} args
 * @returns resolve result and if failed failed parameters list, reject on timeout or wrong command
 */
export function readGprs(args = {}) {
  log.info({ message: 'start of readGprs()', tag: tags.server });
  return new Promise((resolve, reject) => {
    const { serverType, timeout, command } = args;
    const { imei } = store.getState().settings.mainParameters;

    const timer = setTimer(
      reject,
      handleTimeoutParameter(timeout),
      () => {
        log.error({
          message: 'readGprs() --> timer() --> Timeout passed, no data matched',
          tag: tags.server,
        });
        emitter[serverType].removeListener('GPRS', onData);
      },
      'Timeout passed, no data matched'
    );

    const cmd = CommandList.cmdList.find(
      (element) => String(command) === String(element.cmd)
    );
    if (!cmd) {
      clearTimeout(timer);
      log.error({
        message: 'readGprs() --> CMD not found in /bindings/sms/cmdlist.js',
        tag: tags.server,
      });
      return reject(new Error('CMD not found').message);
    }
    emitter[serverType].on('GPRS', onData);
    function onData(packet) {
      if (imei ? Number(imei) !== Number(packet.imei) : false) {
        log.error({ message: 'readGprs() IMEI mismatch', tag: tags.server });
        return null;
      }
      const matchFound = packet.data.response.match(cmd.pattern);
      if (matchFound) {
        log.info({
          message: `readGprs() --> matchFound, data: "${packet.data.response}"`,
          tag: tags.server,
        });
        clearTimeout(timer);
        emitter[serverType].removeListener('GPRS', onData);
        CheckParameters(cmd, packet.data.response)
          .then(() =>
            log.info({
              message: 'readGprs() --> CMD matched --> resolve',
              tag: tags.server,
            })
          )
          .then(() => resolve({ result: true }))
          .catch((failedParameters) => {
            log.error({
              message: 'readGprs() --> CMD not matched --> reject',
              tag: tags.server,
            });
            return resolve({ response: failedParameters, result: false });
          });
      } else {
        log.info({
          message: `readGprs() mismatched data: "${packet.data.response}"`,
          tag: tags.server,
        });
      }
    }
  });
}

/**
 * @description read GPRS commands response and conpare with entered regex
 * @param {{ serverType:string, timeout:{ value:number, units:string }, regex:string }} args
 */
export function readGprsManuallyFunc(args = {}) {
  log.info({ message: 'start of readGprsManuallyFunc()', tag: tags.server });
  return new Promise((resolve, reject) => {
    remakeArgs(args, [], { timestamp: ['min', 'max'] });
    const {
      serverType = 'main',
      timeout,
      regex,
      otherResponses = true,
      timestamp,
    } = args;
    const { imei } = store.getState().settings.mainParameters;
    const wrongResponses = [];

    const timer = setTimeout(() => {
      log.error({
        message:
          'readGprsManuallyFunc() --> timer() --> Timeout passed, no data matched',
        tag: tags.server,
      });
      emitter[serverType].removeListener('GPRS', onData);
      if (wrongResponses.length > 0) {
        return resolve(wrongResponses);
      }
      return reject(new Error('Timeout passed, no data recieved').message);
    }, handleTimeoutParameter(timeout));

    emitter[serverType].on('GPRS', onData);
    function onData(packet) {
      if (imei ? Number(imei) !== Number(packet.imei) : false) {
        log.error({
          message: 'readGprsManuallyFunc() IMEI mismatch',
          tag: tags.server,
        });
        return null;
      }
      const matchFound = packet.data.response.match(regex);
      if (matchFound) {
        log.info({
          message: `readGprsManuallyFunc() --> matchFound, data: "${packet.data.response}"`,
          tag: tags.server,
        });
        /** If timestamp check enabled */
        if (timestamp) {
          log.info({
            message: 'readGprsManuallyFunc() --> timestamp check is enabled',
            tag: tags.server,
          });
          /** Timestamp value between min - max */
          if (
            packet.data.timestamp >= timestamp.min &&
            packet.data.timestamp <= timestamp.max
          ) {
            clearTimeout(timer);
            emitter[serverType].removeListener('GPRS', onData);
            return resolve({
              result: true,
              response: { mached: matchFound[0], all: matchFound.input },
              timestamp: {
                value: packet.data.timestamp,
                min: timestamp.min,
                max: timestamp.max,
              },
            });
          }
          /** Timestam value out of range */
          wrongResponses.push({
            response: packet.data.response,
            responseResult: true,
            timestampValue: packet.data.timestamp,
            timestampMin: timestamp.min,
            timestampMax: timestamp.max,
          });
          if (!otherResponses) {
            clearTimeout(timer);
            emitter[serverType].removeListener('GPRS', onData);
            return resolve(wrongResponses);
          }

          /** If timestamp check disabled */
        } else {
          log.info({
            message:
              'readGprsManuallyFunc() --> timestamp check is disabled --> resolve(...)',
            tag: tags.server,
          });
          resolve({
            result: true,
            response: { mached: matchFound[0], all: matchFound.input },
          });
        }
        /** Wrong response */
      } else {
        log.info({
          message: `readGprsManuallyFunc() mismatched data: "${packet.data.response}"`,
          tag: tags.server,
        });
        wrongResponses.push({
          response: packet.data.response,
          responseResult: false,
        });
        if (!otherResponses) {
          clearTimeout(timer);
          emitter[serverType].removeListener('GPRS', onData);
          return resolve(wrongResponses);
        }
      }
    }
  });
}

/**
 * Send raw data to device via GPRS
 * @param {{ serverType:string, imei:string, rawData:string, rawDataType:string }} args
 * @returns {Promise<null>} resolve null on successfully send
 */
export function sendRawData(args) {
  log.info({ message: 'start of sendRawData()', tag: tags.server });
  const { serverType = 'main', rawData, rawDataType = 'hex' } = args;
  let sendData;
  const { imei } = store.getState().settings.mainParameters;
  return new Promise((resolve, reject) => {
    checkClientStatus({ serverType, connStatus: true, timeout: 0 })
      .then(() => {
        const timer = setTimer(
          reject,
          10 * 1000,
          () => {
            log.error({
              message:
                'sendRawData() --> timer() --> Timeout passed, any status about sending',
              tag: tags.server,
            });
            emitter[serverType].removeListener('GPRS_sending', statusHandle);
          },
          'Timeout passed, any status about sending'
        );

        emitter[serverType].once('GPRS_sending', statusHandle);

        function statusHandle(data) {
          clearTimeout(timer);
          if (data.done) {
            // Successfully sent
            log.info({
              message: 'sendRawData() --> resolve',
              tag: tags.server,
            });
            return resolve(null);
          }
          // Unsuccsessfully
          const err = new Error(
            `sendRawData() --> reject(err) --> err: ${data.error}`
          );
          log.error({ message: err.stack, tag: tags.server });
          return reject(data.error);
        }

        switch (rawDataType) {
          case 'hex': {
            sendData = Buffer.from(rawData, 'hex');
            break;
          }
          case 'ascii': {
            sendData = rawData;
            break;
          }
          default: {
            return reject(new Error('Wrong raw data type format').message);
          }
        }

        const clientId = server[serverType].clients.findIndex(
          (x) => Number(x.info.imei) === Number(imei)
        );
        if (Number(clientId) !== -1) {
          log.info({
            message: `sendRawData() --> sending data do device, sendData: "${sendData}"`,
            tag: tags.server,
          });
          server[serverType].clients[clientId].sendRawData(sendData);
        } else {
          clearTimeout(timer);
          emitter[serverType].removeListener('GPRS_sending', statusHandle);
          log.error({
            message:
              'sendGprsCommand() --> reject(err) --> err: "Client is not connected"',
            tag: tags.server,
          });
          return reject(new Error('Client is not connected').message);
        }
        return null;
      })
      .catch(() => {
        log.error({
          message:
            'sendGprsCommand() --> reject(err) --> err: "Client is not connected"',
          tag: tags.server,
        });
        return reject(new Error('Client is not connected').message);
      });
  });
}

/**
 * @description Reed any raw data got to server
 * @param {{serverType:string, imei:string, timeout: {value:number, units:string}, regex:string, regexFormat:string}} args
 */
export function readRawData(args) {
  return new Promise((resolve, reject) => {
    log.info({ message: 'start of readRawData()', tag: tags.server });
    const {
      serverType = 'main',
      imei,
      timeout,
      regex,
      regexFormat = 'ascii',
      doOnRegexMatch = 'pass',
    } = args;
    const timer = setTimeout(() => {
      emitter[serverType].removeListener('raw', onData);
      if (doOnRegexMatch === 'pass') {
        const error = new Error('Timeout passed, no data matched');
        return reject(error.message);
      }
      return resolve({ result: 'Timeout passed, no data matched as expected' });
    }, handleTimeoutParameter(timeout));

    let localRegex = new RegExp(regex);
    emitter[serverType].on('raw', onData);
    function onData(packet) {
      if (imei ? Number(imei) !== Number(packet.imei) : false) {
        log.error({ message: 'readRawData() IMEI mismatch', tag: tags.server });
        return null;
      }
      log.info({
        message: 'readRawData() --> onData() got new packet',
        tag: tags.server,
      });
      const dataHex = packet.data.toString('hex');
      let matchFound;
      if (regexFormat === 'hex') {
        localRegex = new RegExp(regex.toLowerCase());
        matchFound = dataHex.match(localRegex);
      } else if (regexFormat === 'ascii') {
        matchFound = Buffer.from(dataHex, 'hex')
          .toString('utf8')
          .match(localRegex);
      }
      if (matchFound) {
        log.info({
          message: `readGprsManuallyFunc() --> matchFound, data: "${matchFound}"`,
          tag: tags.server,
        });
        clearTimeout(timer);
        emitter[serverType].removeListener('raw', onData);
        if (doOnRegexMatch === 'pass') {
          log.info({
            message: 'readRawData() --> onData() match found --> resolve',
            tag: tags.server,
          });
          return resolve(matchFound);
        }
        log.info({
          message: 'readRawData() --> onData() match found --> reject',
          tag: tags.server,
        });
        const error = new Error(`Match found: ${matchFound}`);
        return reject(error.message);
      }
      log.info({
        message: `readRawData() --> data mismatch regex, data: "${
          regexFormat === 'hex'
            ? dataHex
            : Buffer.from(dataHex, 'hex').toString('utf8')
        }"`,
        tag: tags.server,
      });
    }
  });
}

/**
 * @description Check/wait client open link status
 * @param {{ serverType?:string, connStatus:boolean, timeout:number, invertResult?:boolean }} args
 */
export function checkClientStatus(args) {
  log.info({ message: 'start of checkClientStatus()', tag: tags.server });
  return new Promise((resolve, reject) => {
    const {
      serverType = 'main',
      connStatus,
      timeout,
      invertResult = false,
    } = args || {};
    const duration = handleTimeoutParameter(timeout);
    const { imei } = store.getState().settings.mainParameters;
    let rejectTimer;
    const isLongTerm = duration > 0;
    let returnInstantly = false;
    const serverTypeList = serverType.split('&');

    // if timeout exists → run reject timer
    if (isLongTerm) {
      log.info({
        message: `checkClientStatus --> Lounch reject timer [${duration}]`,
        tag: tags.server,
      });
      rejectTimer = setTimeout(() => {
        log.info({
          message:
            'checkClientStatus --> rejectTimer passed, set returnInstantly = true; and checkResults() last time',
          tag: tags.server,
        });
        returnInstantly = true;
        checkResults();
      }, duration);
    } else {
      log.info({
        message:
          'checkClientStatus --> tmo undefined --> returnInstantly = true; and checkResults()',
        tag: tags.server,
      });
      returnInstantly = true;
      checkResults();
    }

    function checkResults() {
      log.info({
        message: 'start of checkClientStatus() --> checkResults()',
        tag: tags.server,
      });

      const resultList = [];
      serverTypeList.forEach((_serverType) => {
        const { clients } = store.getState().dataServer[_serverType];
        const clientConnected = !!clients.find(
          (client) => String(client.imei) === String(imei)
        );
        resultList.push(clientConnected);
      });

      const result = Object.fromEntries(
        serverTypeList.map((_serverType, i) => [_serverType, resultList[i]])
      );
      log.info({ message: JSON.stringify(result), tag: tags.server });

      // All values in resultList must be equal
      const isEqual = resultList.every((val, i, arr) => val === arr[0]);

      if (!isEqual) {
        if (!returnInstantly) {
          log.info({ message: `Statuses are different`, tag: tags.server });
          /** Just skip */
          return null;
        }

        log.info({
          message:
            'Need to return result instantly, but connection status are not equal between servers.',
          tag: tags.server,
        });
        removeListeners();
        return reject(
          new Error(
            `Client connection status differs across servers: ${JSON.stringify(
              result
            )}`
          ).message
        );
      }

      const [active] = resultList;
      if (connStatus === active) {
        clearTimeout(rejectTimer);
        removeListeners();
        if (invertResult) {
          log.info({
            message: `checkClientStatus() --> reject --> Client status: ${
              active ? 'connected' : 'disconnected'
            }`,
            tag: tags.server,
          });
          if (isLongTerm) {
            return reject(
              new Error(
                `Expected client not to ${
                  connStatus ? 'connect' : 'disconnect'
                } in ${duration}ms, but it did`
              ).message
            );
          }
          return reject(
            new Error(
              `Expected client not to be ${
                connStatus ? 'connected' : 'disconnected'
              }, but it is`
            ).message
          );
        }
        log.info({
          message: 'checkClientStatus() --> resolve',
          tag: tags.server,
        });
        return resolve(null);
      }
      if (returnInstantly) {
        removeListeners();
        if (invertResult) {
          log.info({
            message: 'checkClientStatus() --> resolve',
            tag: tags.server,
          });
          return resolve(null);
        }
        log.error({
          message: `checkClientStatus() --> Client status: ${
            active ? 'connected' : 'disconnected'
          }`,
          tag: tags.server,
        });

        if (isLongTerm) {
          return reject(
            new Error(
              `Expected client to ${
                connStatus ? 'connect' : 'disconnect'
              } in ${duration} ms, but it did not`
            ).message
          );
        }
        return reject(
          new Error(
            `Expected client to be ${
              connStatus ? 'connected' : 'disconnected'
            }, but it is not`
          ).message
        );
      }
    }

    // Check imei and call checkResults function
    function handleCheckResults(device) {
      if (String(device.imei) === String(imei)) {
        checkResults();
      }
    }

    // Remove event listeners
    function removeListeners() {
      serverTypeList.forEach((_serverType) => {
        emitter[_serverType].removeListener(
          'authenticated',
          handleCheckResults
        );
        emitter[_serverType].removeListener(
          'connection_lost',
          handleCheckResults
        );
      });
    }

    // Listen for events
    if (!returnInstantly) {
      serverTypeList.forEach((_serverType) => {
        emitter[_serverType].on('authenticated', handleCheckResults);
        emitter[_serverType].on('connection_lost', handleCheckResults);
      });

      // Call checkResults function to check if we can return result immediately
      checkResults();
    }
  });
}

/**
 * @description Forse close client open link
 * @param {*} args
 */
export function closeLink(args) {
  log.info({ message: 'start of closeLink()', tag: tags.server });
  const { serverType = 'main' } = args;
  const { imei } = store.getState().settings.mainParameters;
  const timeout = 10 * 1000;
  return new Promise((resolve, reject) => {
    const timer = setTimer(reject, timeout, null, 'Timeout');
    switch (serverType) {
      case 'main': {
        server[serverType].forceClose(imei);
        break;
      }
      case 'duplicate': {
        server[serverType].forceClose(imei);
        break;
      }
      case 'third': {
        server[serverType].forceClose(imei);
        break;
      }
      case 'both': {
        server.main.forceClose(imei);
        if (server.duplicate !== null) {
          server.duplicate.forceClose(imei);
        }
        if (server.third !== null) {
          server.third.forceClose(imei);
        }
        break;
      }
      default:
        clearTimeout(timer);
        log.error({
          message: 'closeLink() --> Wrong serverType --> reject()',
          tag: tags.server,
        });
        return reject(new Error('Wrong serverType').message);
    }
    clearTimeout(timer);
    log.info({ message: 'closeLink() --> resolve(null)', tag: tags.server });
    return resolve(null);
  });
}

/**
 * Checking Open Link Timeout and compare with configured
 * @param {String} args.serverType - Defines server (main, duplicate or third)
 * @param {Object} args.timeout - Set max acton time. timeout = { value, units }
 * @param {Object} args.linkTimeout - Defines configured open link timeout. linkTimeout = { value, units }
 * @returns {Promise} { result: true/false }
 */
export function checkLinkTimeout(args) {
  log.info({ message: 'start of checkLinkTimeout()', tag: tags.server });
  const { serverType = 'main', timeout, linkTimeout, mustClose = true } = args;
  const permissibleError = 2000;
  const { imei } = store.getState().settings.mainParameters;

  return new Promise((resolve, reject) => {
    const link = {
      openedAt: null,
      isOpen: false,
    };
    const _timeout = handleTimeoutParameter(timeout);

    if (mustClose) {
      setTimer(reject, _timeout, () => {
        emitter[serverType].removeListener('authenticated', connection);
        emitter[serverType].removeListener('record', record);
        emitter[serverType].removeListener('connection_lost', connectionLost);
      });
    } else {
      setTimeout(() => {
        emitter[serverType].removeListener('authenticated', connection);
        emitter[serverType].removeListener('record', record);
        emitter[serverType].removeListener('connection_lost', connectionLost);
        if (link.isOpen) return resolve({ result: true });
        return reject(new Error('Link is not opened.').message);
      }, _timeout);

      checkClientStatus({ serverType, connStatus: true, timeout: 0 })
        .then(() => {
          link.isOpen = true;
          connection({ imei });
          return null;
        })
        .catch(() => null);
    }

    function connection(device) {
      if (Number(device.imei) !== Number(imei)) {
        log.info({
          message:
            'checkLinkTimeout() --> connection --> IMEI mismatch --> ignore',
          tag: tags.server,
        });
        return null;
      }

      link.openedAt = new Date().getTime();
      link.isOpen = true;

      emitter[serverType].removeListener('authenticated', connection);

      emitter[serverType].on('connection_lost', connectionLost);
      emitter[serverType].on('record', record);
    }

    function record() {
      log.info({
        message: 'checkLinkTimeout() got record. Set openedAt to now',
        tag: tags.server,
      });

      link.openedAt = new Date().getTime();
    }

    function connectionLost(device) {
      if (Number(device.imei) !== Number(imei)) {
        log.info({
          message:
            'checkLinkTimeout() --> connectionLost --> IMEI mismatch --> ignore',
          tag: tags.server,
        });
        return null;
      }
      emitter[serverType].removeListener('connection_lost', connectionLost);
      log.info({
        message: 'checkLinkTimeout() client disconnected',
        tag: tags.server,
      });
      link.isOpen = false;
      emitter[serverType].removeListener('record', record);
      const openTime = new Date().getTime() - link.openedAt;
      const diff = Math.abs(openTime - handleTimeoutParameter(linkTimeout));
      log.info({
        message: `checkLinkTimeout() --> Open link time: ${openTime} ms; Diffence: ${diff} ms`,
        tag: tags.server,
      });

      const result = diff < permissibleError;
      log.info({
        message: `checkLinkTimeout() --> Is difference (${diff}) less than permissible error (${permissibleError}): ${result}`,
        tag: tags.server,
      });
      if (mustClose) {
        log.info({
          message: `checkLinkTimeout() --> must close true --> resolve({ result:${result} })`,
          tag: tags.server,
        });
        return resolve({ result });
      }
      log.info({
        message:
          'checkLinkTimeout() --> must close false --> Link was closed --> reject',
        tag: tags.server,
      });
      return reject(new Error('Link was closed').message);
    }
    emitter[serverType].on('authenticated', connection);
  });
}

/**
 * Check recors sorting in packet (oldest/ newest)
 * @param {number} args.timeout.value - All time for collect records
 * @param {string} args.timeout.units - posible unist 'ms' - miliseconds; 's' - seconds, 'min' - minutes, h - hours
 * @param {number} settings.timeout - Default time for collect records, if don't set args.timeout
 * @returns {Promise} { sortBy: result } result: 'oldest' / 'newest
 */
export function recordsSorting(args) {
  log.info({ message: 'start of recordsSorting()', tag: tags.server });
  return new Promise((resolve, reject) => {
    const { timeout = { value: 5, units: 'min' } } = args;
    const time = handleTimeoutParameter(timeout);

    const timestampStartAction = new Date().valueOf();
    setTimeout(() => {
      const records = [];
      const { imei } = store.getState().settings.mainParameters;
      const allRecords =
        store.getState().dataServer.main.avlRecords[imei] || [];

      allRecords.forEach((record) => {
        if (
          record.info.timestamp > timestampStartAction &&
          record.record.priority <= 1
        )
          records.push(record);
      });

      const recordPackets = [];
      let recordPacket = [];
      let timestampSend = 0;

      records.forEach((record) => {
        if (
          record.info.timestamp !== timestampSend &&
          recordPacket.length === 0
        ) {
          timestampSend = record.info.timestamp;
          recordPacket.push(record);
        } else if (record.info.timestamp === timestampSend) {
          recordPacket.push(record);
        } else if (
          record.info.timestamp !== timestampSend &&
          recordPacket.length > 0
        ) {
          timestampSend = record.info.timestamp;
          recordPackets.push(recordPacket);
          recordPacket = [record];
        }
      });

      if (recordPacket.length > 0) {
        recordPackets.push(recordPacket);
      }

      const resultArray = [];

      recordPackets.forEach((packet) => {
        let tempRec;
        packet.forEach((rec) => {
          if (!tempRec) {
            tempRec = rec.record.timestamp;
          } else if (rec.record.timestamp < tempRec) {
            resultArray.push('newest');
          } else if (rec.record.timestamp > tempRec) {
            resultArray.push('oldest');
          } else {
            return reject(new Error('Duplicate record').message);
          }
        });
      });

      let result;
      if (resultArray.length === 0) {
        log.info({
          message: 'recordsSorting() record list empty --> reject',
          tag: tags.server,
        });
        return reject(new Error('Not tested, need more records.').message);
      }

      resultArray.forEach((res) => {
        if (!result) {
          result = res;
        } else if (String(result) !== String(res)) {
          log.error({
            message:
              'recordsSorting() Bad order of record timestamps --> reject',
            tag: tags.server,
          });
          return reject(new Error('Bad order of timestamps').message);
        }
      });

      result = { sortBy: result };
      log.info({
        message:
          'recordsSorting() got enough records with good timestamps --> resolve',
        tag: tags.server,
      });
      return resolve(result);
    }, time);
  });
}

/**
 * Check for duplicate records.
 */
export function recordDuplicate(args) {
  log.info({ message: 'start of recordDuplicate()', tag: tags.server });
  const { serverType = 'main' } = args;
  return new Promise((resolve, reject) => {
    const { imei } = store.getState().settings.mainParameters;
    const records = store.getState().dataServer[serverType].avlRecords[imei];
    if (!records) return reject(new Error('Records does not exist').message);

    const timestamps = records
      .map((record) => record.record.timestamp)
      .slice()
      .sort();
    if (timestamps.length < 2) {
      log.info({
        message:
          'recordDuplicate() --> not enough records (records < 2) --> reject',
        tag: tags.server,
      });
      return reject(new Error('Not enough records (records < 2)').message);
    }
    const results = [];
    for (let i = 0; i < timestamps.length - 1; i += 1) {
      if (timestamps[i + 1] === timestamps[i]) {
        results.push(timestamps[i]);
      }
      if (i === timestamps.length - 2 && results.length === 0) {
        log.info({
          message: 'recordDuplicate() --> got results --> resolve',
          tag: tags.server,
        });
        return resolve(null);
      }
      if (i === timestamps.length - 2 && results.length > 0) {
        log.error({
          message: `recordDuplicate() --> got results --> reject(${results})`,
          tag: tags.server,
        });
        return reject(results);
      }
    }
  });
}

export function getResultsBasedOnParams(args) {
  return new Promise((resolve) => {
    const { finalPacket, userParameters, reqpacket } = args || {};
    /* Create result based duplicate object */
    const packetParameters = { ...userParameters };
    let result = true;
    Object.keys(userParameters).forEach((expectedKey) => {
      getAIS140packet(reqpacket).forEach((param, idx) => {
        /* [trackingPacket] OR any other packet from mapMyIndia.js */
        /* proceed only if correct parameter is found */
        if (expectedKey === param) {
          packetParameters[param] = finalPacket[idx];
          /* Compare user-defined parameters versus parameters from collected packet */
          if (
            !`${finalPacket[idx]}`.match(
              new RegExp(userParameters[expectedKey])
            )
          ) {
            /* Parameters does not match → action status FAILED */
            result = false;
          }
        }
      });
    });
    return resolve({ result, packetParameters });
  });
}

export function validAIS140packet(args) {
  return new Promise((resolve) => {
    const { finalPacket, otherRecords, reqpacket } = args || {};
    /* Check if all parsed packets are valid */
    for (let i = 0; i < Object.keys(finalPacket).length; i += 1) {
      /* Get current packet length */
      const currentPacketLength = Object.values(finalPacket)[i].length;
      /* Get current packet name by its length */
      const currentPacketName = getAIS140packet(currentPacketLength);
      /* Check if we've got unknown packet */
      const unknownPacketExists = currentPacketName.includes('unknown');
      if (unknownPacketExists) {
        /* unknown packet is found → reject ERROR */ return resolve({
          result: false,
          packet: `${currentPacketName} received!`,
          data: `\n${Object.values(finalPacket)[i]}\n`,
        });
      }
      const [firstRecord] =
        Object.values(finalPacket); /* Define first record */
      /* Check if first record is the record we need */
      if (
        !otherRecords &&
        getAIS140packet(reqpacket).length !== firstRecord.length
      ) {
        return resolve({
          result: false,
          packet: `${getAIS140packet(firstRecord.length)} received!`,
          data: `\n${firstRecord}\n`,
        });
      }
    }
    return resolve(null);
  });
}

export function handleResults(args) {
  return new Promise((resolve, reject) => {
    const {
      otherRecords,
      finalPacket,
      userParameters,
      reqpacket,
      packetData,
      packetResults,
    } = args || {};
    /* Scan through all records inside packet of records and check if "reqpacket" is found */
    if (otherRecords) {
      // finalPacket
      (function cycle(index = 0) {
        const packetLength = finalPacket.length;
        const currentRecord = Object.values(finalPacket)[index];
        getResultsBasedOnParams({
          finalPacket: currentRecord,
          userParameters,
          reqpacket,
        })
          .then((results) => {
            const { result } = results;
            if (!result && index < packetLength) {
              return cycle(index + 1);
            }
            if (result) {
              return resolve(results);
            }
            return reject(
              new Error(
                `Packet of [${packetResults}] recs received but such record not found!`
              ).message
            );
          })
          .catch((err) => {
            /* nothing is rejected */ throw err;
          });
      })();
    } /* Check only first record inside packet */ else {
      const [firstRecord] = Object.values(finalPacket);
      const [recName] = Object.keys(finalPacket)[0].split('_');
      /* Check if that record is which we need */
      if (recName !== reqpacket) {
        return resolve({
          result: false,
          info: `${recName} received!`,
          packetData,
        });
      }
      getResultsBasedOnParams({
        finalPacket: firstRecord,
        userParameters,
        reqpacket,
      })
        .then(resolve)
        .catch((err) => {
          /* nothing is rejected */ throw err;
        });
    }
  });
}

export function checkIfRecordExists(args) {
  return new Promise((resolve) => {
    const { finalPacket, reqpacket } = args || {};
    let found = false;
    /* Skip other packets if "reqpacket" does not exists */
    for (const subPacket of Object.keys(finalPacket)) {
      const [packetName] = subPacket.split('_');
      if (packetName === reqpacket) {
        found = true;
      }
    }
    return resolve(found);
  });
}

/* Documentation: https://gps-gitlab.teltonika.lt/fleet/fmb/fmb-documentation/blob/master/Spec Projects/FMB.SpecId_114 Functionality Description.doc */
export function specMapMyIndia(args = {}) {
  return new Promise((resolve, reject) => {
    log.info({ message: 'start of specMapMyIndia()', tag: tags.server });
    const {
      returnOnly,
      otherRecords,
      reqpacket,
      ignoreOthers,
      imei,
      regex,
      regexFormat,
      serverType,
      timeout,
      ...userParameters
    } = args;

    /* Start timeout in case of failure */
    const timer = setTimer(
      reject,
      handleTimeoutParameter(timeout),
      () => {
        emitter[serverType].removeListener('AIS-140', handlePacket);
      },
      'Timeout passed'
    );
    async function handlePacket(packet) {
      const { buffer, data } = packet || {};
      log.info({
        message: `[0] New packet received! buffer[${buffer.toString()}] data[${JSON.stringify(
          data
        )}]`,
        tag: tags.server,
      });

      /* Convert buffer to string */
      const packetData = buffer.toString();

      /* Collect array with parsed data */
      const finalPacket =
        data; /* [ loginPacket ] or [ trackingPacket, trackingPacket ] or [ trackingPacket, healthPacket ] */
      const packetResults = JSON.stringify(finalPacket).replace(/"/g, '');

      /** @regex   parameter priority: 1 Check packet by user defined regex */
      if (regex && regex.length > 0) {
        /* Length check on packet includes ? */
        log.info({
          message: `[2] if (ignoreOthers[${ignoreOthers}])`,
          tag: tags.server,
        });
        if (ignoreOthers) {
          /* If whole packet matches regex */
          log.info({
            message: `[3] if (${packetData.match(
              new RegExp(regex)
            )} || ${packetData.includes(regex)})`,
            tag: tags.server,
          });
          if (
            packetData.match(new RegExp(regex)) ||
            packetData.includes(regex)
          ) {
            return resolve({ result: true, packet: packetData });
          }
          log.info({
            message: '[4] skip and wait action timeout',
            tag: tags.server,
          });
          // skip and wait for action timeout
          return null;
        }
        log.info({
          message:
            '[5] ignoreOthers = false ---> check regex and return results',
          tag: tags.server,
        });
        if (packetData.match(new RegExp(regex)) || packetData.includes(regex)) {
          return resolve({ result: true, packet: packetData });
        }
        /* Not matched → reject with packet data and indication if login packet was removed */
        return resolve({ result: false, packet: packetData });
      }

      /**
       * @returnOnly parameter priority: 2
       */
      log.info({
        message: '[6] regex was not defined. Check returnOnly parameter...',
        tag: tags.server,
      });
      /* Check if user requires default packet inside results */
      if (typeof returnOnly === 'boolean' && returnOnly) {
        /* Return data and do not check anything */ log.info({
          message: '[7] returnOnly was set to TRUE --> resolve packet data',
          tag: tags.server,
        });
        return resolve({ result: true, packetData });
      }

      log.info({
        message: `[8] if (returnOnly is string ? [${
          typeof returnOnly === 'string'
        }])`,
        tag: tags.server,
      });
      /* wait for specific record and return it */
      if (typeof returnOnly === 'string') {
        log.info({
          message: '[9] check if required packet is received...',
          tag: tags.server,
        });
        for (let i = 0; i < Object.keys(finalPacket).length; i += 1) {
          const [packetName] = Object.keys(finalPacket)[i].split('_');
          log.info({
            message: `[10] if (returnOnly === packetName [${
              returnOnly === packetName
            }])`,
            tag: tags.server,
          });
          if (returnOnly === packetName) {
            const singleRecord = Object.values(finalPacket)[i];
            return resolve({
              result: true,
              [packetName]: singleRecord.join(','),
            });
          }
        }
        if (ignoreOthers) {
          log.info({
            message: '[11] Ignore others param enabled. SKIP!',
            tag: tags.server,
          });
          /* Skip if record is not found */
          return null;
        }
        log.info({
          message: '[12] Ignore others param disabled. reject()',
          tag: tags.server,
        });
        return resolve({
          result: false,
          message: `Packet of [${packetResults}] recs received but "${returnOnly}" not found!`,
        });
      }

      let exists = false;
      log.info({
        message: '[13] Skip other packets if "reqpacket" does not exists',
        tag: tags.server,
      });
      /* Skip other packets if "reqpacket" does not exists */
      await checkIfRecordExists({ finalPacket, reqpacket })
        .then((found) => {
          if (found) {
            /* "reqpacket" is found */
            exists = true;
          }
          return null;
        })
        .catch((err) => {
          /* nothing is rejected */ throw err;
        });
      if (!exists && ignoreOthers) {
        log.info({
          message: '[14] !exists && ignoreOthers ---> true',
          tag: tags.server,
        });
        return null;
      }
      if (!exists && !ignoreOthers) {
        log.info({
          message: '[15] !exists && !ignoreOthers ---> true',
          tag: tags.server,
        });
        return resolve({
          result: false,
          message: `Packet of [${packetResults}] recs received but "${reqpacket}" not found!`,
        });
      }

      log.info({
        message:
          '[16] Regex is not defined; 2. Return only is false → Check parameters and return results',
        tag: tags.server,
      });
      /* 1. Regex is not defined; 2. Return only is false → Check parameters and return results */
      validAIS140packet({ finalPacket, otherRecords, reqpacket })
        .then((result) => {
          if (result !== null) {
            return resolve(result);
          }
          return null;
        })
        .then(() =>
          handleResults({
            ignoreOthers,
            otherRecords,
            finalPacket,
            userParameters,
            reqpacket,
            packetData,
            packetResults,
          })
        )
        .then(resolve)
        .then(() => {
          /* Remove previously created event listener 'AIS-140' */
          emitter[serverType].removeListener('AIS-140', handlePacket);

          /* Remove ongoing timer */
          clearTimeout(timer);
          return null;
        })
        .catch(reject);
    }
    /* Wait For AIS-140 packet and emit it to handlePacket f-tion */
    emitter[serverType].on('AIS-140', handlePacket);
  });
}

export function addAesKeyToServer(args) {
  log.info({ message: 'start of addAesKeyToServer()', tag: tags.server });
  return new Promise((resolve) => {
    const { serverType = 'main', keyName, keyValue } = args;
    server[serverType].addKeyToAesKeylist(keyName, keyValue);
    return resolve(null);
  });
}

export function sendTavlSms(args) {
  log.info({ message: 'start of sendTavlSms()', tag: tags.server });
  return new Promise((resolve, reject) => {
    const { text, customNmb, encoding } = args;
    const { gsmNumber } = store.getState().settings.mainParameters;
    // eslint-disable-next-line camelcase
    const { public_ip } = store.getState().settings.ports;
    if (!text || (text && text.length === 0)) {
      return reject(new Error('Empty text field!').message);
    }
    let encodedData;
    if (encoding && encoding !== 'none') {
      switch (encoding) {
        case 'spec118':
          encodedData = spec118Encoding(
            text,
            public_ip
          ); /** cia npralest per funkcija */
          if (
            encodedData ===
            // eslint-disable-next-line camelcase
            `Input is not valid. Must be [setparam 2004:${public_ip}]`
          ) {
            return reject(new Error(encodedData).message);
          }
          break;
        default:
          return reject(
            new Error('Wrong value of "encoding" parameter.').message
          );
      }
    }

    const buffer = (params) => {
      const { destNum, textMsg } = params || {};
      const msgLength = Buffer.alloc(2);
      msgLength[1] = textMsg.length;
      const arr = [
        Buffer.from([1]),
        Buffer.from([3]),
        Buffer.from([destNum.length]),
        Buffer.from(destNum),
        msgLength,
        Buffer.from(textMsg),
        Buffer.from([2]),
      ];
      const packetLength = Buffer.alloc(2);
      packetLength[1] = Buffer.concat(arr).length + 2;
      return Buffer.concat([packetLength, ...arr]);
    };

    const client = new net.Socket();

    client.connect(19898, '88.119.140.169', () => {
      if (
        (customNmb && !customNmb.includes('3706')) ||
        (customNmb && customNmb.length !== 11)
      ) {
        return reject(new Error('Wrong GSM number from the action!').message);
      }
      if (
        !customNmb &&
        (!gsmNumber || (gsmNumber && !gsmNumber.includes('3706')))
      ) {
        return reject(new Error('Unknown device GSM number!').message);
      }
      const correctNumber =
        customNmb || (gsmNumber[0] === '+' ? gsmNumber.substr(1) : gsmNumber);
      client.write(
        buffer({ destNum: correctNumber, textMsg: encodedData || text })
      );
    });

    client.on('data', () => {
      client.destroy(); // kill client after server's response
      return resolve(null);
    });
  });
}

/*
    Generate iButtons automatically
    -------------------------------
*/
function GPRSreadGetIbutton(args) {
  return new Promise((resolve, reject) => {
    const { index, serverType, currentRandomIbutton, param } = args || {};
    const { imei } = store.getState().settings.mainParameters;

    const timer = setTimer(
      reject,
      20 * 1000,
      () => {
        emitter[serverType].removeListener('GPRS', handleReadData);
      },
      'GPRSreadGetIbutton timeout passed'
    );

    emitter[serverType].on('GPRS', handleReadData);

    function handleReadData(packet) {
      if (imei === packet.imei) {
        const { response } = packet.data || {};
        const paramResp = param
          ? `Param ID:${index} Value:${currentRandomIbutton}`
          : `iButton ${currentRandomIbutton}`;
        if (response === paramResp) {
          clearTimeout(timer);
          emitter[serverType].removeListener('GPRS', handleReadData);
          return resolve(null);
        }
      }
    }
  });
}

function GPRSreadSetIbutton(args) {
  log.info({
    message: 'start of GPRSreadSetIbutton()',
    tag: tags.serialInterface,
  });
  const { index, serverType, currentRandomIbutton, param } = args || {};
  return new Promise((resolve, reject) => {
    const { imei } = store.getState().settings.mainParameters;

    const timer = setTimer(
      reject,
      60 * 1000,
      () => {
        log.info({
          message: 'start of GPRSreadSetIbutton() --> timeout',
          tag: tags.serialInterface,
        });
        emitter[serverType].removeListener('GPRS', handleReadData);
      },
      'GPRSreadSetIbutton timeout passed'
    );

    emitter[serverType].on('GPRS', handleReadData);

    function handleReadData(packet) {
      if (imei === packet.imei) {
        const { response } = packet.data || {};
        const paramResp = param
          ? `New value ${index}:${currentRandomIbutton};`
          : `iButton nr ${index} flashed. Value: ${currentRandomIbutton}`;
        if (response === paramResp) {
          clearTimeout(timer);
          emitter[serverType].removeListener('GPRS', handleReadData);
          return resolve(null);
        }
      }
    }
  });
}

export async function generateIbuttons(args, settings) {
  log.info({
    message: 'start of generateIbuttons()',
    tag: tags.serialInterface,
  });
  remakeArgs(args, ['numberOfIbuttons', 'iButtonLength'], {});
  const {
    type,
    numberOfIbuttons = 1,
    iButtonLength = 16,
    portType = 'device',
    serverType = 'main',
  } = args;
  if (type === 'serial') {
    await checkComPort(portType);
  }
  return new Promise((resolve, reject) => {
    const iButtonsForWriting = [];
    const failedReadParams = [];
    let failedWriteParams = [];
    let result = true;

    const getRanHex = (iButtonSize) => {
      const hexResult = [];
      const hexRef = [
        '0',
        '1',
        '2',
        '3',
        '4',
        '5',
        '6',
        '7',
        '8',
        '9',
        'A',
        'B',
        'C',
        'D',
        'E',
        'F',
      ];
      for (let n = 0; n < iButtonSize; n += 1) {
        hexResult.push(hexRef[Math.floor(Math.random() * 16)]);
      }
      return hexResult.join('');
    };

    const handleSerialErrors = () => {
      sendSerialCommand({
        command: '.log:1',
        regex: /Log Enabled for UART\[[23]\]/,
      })
        .then(() =>
          resolve({
            result,
            type: 'serial',
            failedWriteParams,
            failedReadParams,
          })
        )
        .catch((err) => reject(err));
    };

    function serialReadParams(index = 30000, iButtonIdx = 0) {
      getparamCFG({ id: index, regex: `<GETPARAM>${index}:[0-9A-Fa-f]+` })
        .then((stringFromLog) => {
          const [, readIbuttonValue] = stringFromLog.split(`${index}:`);
          if (
            readIbuttonValue !== iButtonsForWriting[iButtonIdx].value ||
            readIbuttonValue.length !== iButtonLength
          ) {
            failedReadParams.push({
              param: index,
              value: iButtonsForWriting[iButtonIdx].value,
              readValue: readIbuttonValue,
            });
            result = false;
          }
          if (iButtonIdx < numberOfIbuttons - 1) {
            return serialReadParams(index + 1, iButtonIdx + 1);
          }
          return handleSerialErrors();
        })
        .catch(() => {
          failedReadParams.push({
            param: index,
            value: iButtonsForWriting[iButtonIdx].value,
            readValue: 'Failed to get',
          });
          result = false;
          if (iButtonIdx < numberOfIbuttons - 1) {
            return serialReadParams(index + 1, iButtonIdx + 1);
          }
          return handleSerialErrors();
        });
    }

    function saveSerial(iButtonIdx) {
      log.info({
        message: 'start of generateIbuttons() -->> saveSerial()',
        tag: tags.serialInterface,
      });
      for (let i = 0; i < numberOfIbuttons; i += 1) {
        const randomVal = getRanHex(iButtonLength);
        iButtonsForWriting.push({ param: iButtonIdx + i, value: randomVal });
        if (i === numberOfIbuttons - 1) {
          callWriteConfiguration(iButtonsForWriting)
            // eslint-disable-next-line no-loop-func
            .then((res) => {
              failedWriteParams = res;
              if (failedWriteParams.length > 0) {
                result = false;
              }
              return serialReadParams();
            })
            .catch((err) => {
              sendSerialCommand({
                command: '.log:1',
                regex: /Log Disabled for UART\[[23]\]/,
              })
                .then(() => reject(new Error(err).message))
                .catch(reject);
            });
        }
      }
    }

    function saveGPRScycle(index, iButtonIdx, param) {
      const currentRandomIbutton = getRanHex(iButtonLength);
      const setCommand = param
        ? `setparam ${index}:${currentRandomIbutton}`
        : `setibutton ${index},${currentRandomIbutton}`;
      const getCommand = param ? `getparam ${index}` : `getibutton ${index}`;
      checkClientStatus({ serverType, connStatus: true, timeout: 0 })
        .then(() => sendGprsCommand({ command: setCommand }))
        .then(() =>
          GPRSreadSetIbutton({
            index,
            serverType,
            currentRandomIbutton,
            param,
          })
        )
        .then(() => sendGprsCommand({ command: getCommand }))
        .then(() =>
          GPRSreadGetIbutton({
            index,
            serverType,
            currentRandomIbutton,
            param,
          })
        )
        .then(() => {
          if (iButtonIdx < numberOfIbuttons - 1) {
            return saveGPRScycle(index + 1, iButtonIdx + 1, param);
          }
          return resolve({ result, type: 'gprs', failedReadParams });
        })
        .catch((err) => {
          if (`${err}`.includes('Client')) {
            return reject(err);
          }
          failedReadParams.push({ param: index, value: currentRandomIbutton });
          result = false;
          if (iButtonIdx < numberOfIbuttons - 1) {
            return saveGPRScycle(index + 1, iButtonIdx + 1, param);
          }
          return resolve({ result, type: 'gprs', failedReadParams });
        });
    }

    if (type === 'gprsibutton') {
      saveGPRScycle(1, 0, false);
    } else if (type === 'gprsparam') {
      saveGPRScycle(30000, 0, true);
    } else if (type === 'serial') {
      sendSerialCommand(
        { command: '.log:0', regex: /Log Disabled for UART\[[23]\]/ },
        settings
      )
        .then(() => saveSerial(30000))
        .catch((err) => reject(err));
    }
  });
}
/*
    -------------------------------
    Generate iButtons automatically
*/

export function collectRecordsAIS140(args = {}) {
  return new Promise((resolve, reject) => {
    log.info({
      message: 'start of collectRecordsAIS140(args)',
      tag: tags.serialInterface,
    });
    const { serverType, timeout, priorities } = args;
    const time = handleTimeoutParameter(timeout);
    log.info({
      message: `collectRecordsAIS140(args) --> tmo[${time}] --> wait for timeout`,
      tag: tags.serialInterface,
    });
    const collectedRecs = [
      /* collected records data */
    ];
    /* push packet data */
    function handlePacket(packet) {
      log.info({
        message:
          'collectRecordsAIS140(args) --> push packet data to collectedRecs array',
        tag: tags.serialInterface,
      });
      collectedRecs.push(packet.data);
    }
    /* Handle results on timeout */
    setTimeout(() => {
      log.info({
        message: 'collectRecordsAIS140(args) --> timeout reached!',
        tag: tags.serialInterface,
      });
      /* Remove previously created event listener 'AIS-140' */
      emitter[serverType].removeListener('AIS-140', handlePacket);
      const collectedNames = [
        /** (@SPEC 114) AIS-140 @example: loginPacket_x, trackingPacket_x, emergencyPacket_x, healthMonitoringPacket_x */
        /** (@SPEC 147) Kerala @example : NRM_x, FUL_x, EPB_x, ALT_x, CRT_x, BTH_x, ACK_x, HLM_x, LGN_x */
      ];
      let resultMsg = '';
      let result = true;
      const orders = priorities ? priorities.split(',') : [];
      /* Push record types */
      for (const collectedRecord of collectedRecs) {
        for (const recordName of Object.keys(collectedRecord)) {
          collectedNames.push(recordName);
        }
      }
      log.info({
        message: `collectRecordsAIS140(args) --> timeout --> collectedNames: ${JSON.stringify(
          collectedNames,
          null,
          4
        )}`,
        tag: tags.serialInterface,
      });
      if (collectedNames.length === 0) {
        return reject(new Error('No records received!').message);
      }
      /* Check results */
      for (const [index, requiredRec] of orders.entries()) {
        const serverRec = collectedNames[index] || false;
        if (!serverRec) {
          result = false;
        }
        if (requiredRec && serverRec && !serverRec.includes(requiredRec)) {
          resultMsg += `${requiredRec} --> ${serverRec}\n[NOT OK]\n\n`;
          result = false;
        } else if (
          requiredRec &&
          serverRec &&
          serverRec.includes(requiredRec)
        ) {
          resultMsg += `${requiredRec} --> ${serverRec}\n[OK]\n\n`;
        }
      }
      log.info({
        message: `collectRecordsAIS140(args) --> tmo --> result: ${result} resultMsg: ${resultMsg}`,
        tag: tags.serialInterface,
      });
      if (result && resultMsg === '') {
        return resolve(null);
      }
      return reject(new Error(resultMsg).message);
    }, time);
    /* Wait For AIS-140 packet and emit it to handlePacket f-tion */
    emitter[serverType].on('AIS-140', handlePacket);
  });
}

function checkPriorities(args) {
  return new Promise((resolve, reject) => {
    const { collectedRecords, priorities, order_by: orderBy } = args;
    const records = [...collectedRecords];
    let passed = true;

    const returnResults = (reordered) => {
      const detailedResult = detailedCompare(reordered, collectedRecords);
      const { updatedParams, deletedParams, addedParams } =
        detailedResult || {};
      const updateComp = Object.keys(updatedParams || {}).length === 0;
      const deleteComp = Object.keys(deletedParams || {}).length === 0;
      const addComp = Object.keys(addedParams || {}).length === 0;
      if (updateComp && deleteComp && addComp) {
        return resolve({ result: passed });
      }
      return resolve({
        result: false,
        expectedRecords: reordered,
        collectedRecords,
      });
    };

    switch (true) {
      case priorities === 'asc' && orderBy === 'asc': {
        const lowArr = records.filter((el) => el.priority === 0);
        if (lowArr.length === 0) passed = false;
        const lowAscTimestamp = lowArr.sort(
          (a, b) => parseInt(a.timestamp) - parseInt(b.timestamp)
        );
        let reordered = [...lowAscTimestamp];
        const highArr = records.filter((el) => el.priority === 1);
        if (highArr.length === 0) passed = false;
        const highAscTimestamp = highArr.sort(
          (a, b) => parseInt(a.timestamp) - parseInt(b.timestamp)
        );
        reordered = [...reordered, ...highAscTimestamp];
        return returnResults(reordered);
      }
      case priorities === 'asc' && orderBy === 'desc': {
        const lowArr = records.filter((el) => el.priority === 0);
        if (lowArr.length === 0) passed = false;
        const lowDescTimestamp = lowArr.sort(
          (a, b) => parseInt(b.timestamp) - parseInt(a.timestamp)
        );
        let reordered = [...lowDescTimestamp];
        const highArr = records.filter((el) => el.priority === 1);
        if (highArr.length === 0) passed = false;
        const highDescTimestamp = highArr.sort(
          (a, b) => parseInt(b.timestamp) - parseInt(a.timestamp)
        );
        reordered = [...reordered, ...highDescTimestamp];
        return returnResults(reordered);
      }
      case priorities === 'desc' && orderBy === 'desc': {
        const highArr = records.filter((el) => el.priority === 1);
        if (highArr.length === 0) passed = false;
        const highDescTimestamp = highArr.sort(
          (a, b) => parseInt(b.timestamp) - parseInt(a.timestamp)
        );
        let reordered = [...highDescTimestamp];
        const lowArr = records.filter((el) => el.priority === 0);
        if (lowArr.length === 0) passed = false;
        const lowDescTimestamp = lowArr.sort(
          (a, b) => parseInt(b.timestamp) - parseInt(a.timestamp)
        );
        reordered = [...reordered, ...lowDescTimestamp];
        return returnResults(reordered);
      }
      case priorities === 'desc' && orderBy === 'asc': {
        const highArr = records.filter((el) => el.priority === 1);
        if (highArr.length === 0) passed = false;
        const highAscTimestamp = highArr.sort(
          (a, b) => parseInt(a.timestamp) - parseInt(b.timestamp)
        );
        let reordered = [...highAscTimestamp];
        const lowArr = records.filter((el) => el.priority === 0);
        if (lowArr.length === 0) passed = false;
        const lowAscTimestamp = lowArr.sort(
          (a, b) => parseInt(a.timestamp) - parseInt(b.timestamp)
        );
        reordered = [...reordered, ...lowAscTimestamp];
        return returnResults(reordered);
      }

      case priorities === 'none' && orderBy === 'desc': {
        const descTimestamp = records.sort(
          (a, b) => parseInt(b.timestamp) - parseInt(a.timestamp)
        );
        return returnResults(descTimestamp);
      }
      case priorities === 'none' && orderBy === 'asc': {
        const ascTimestamp = records.sort(
          (a, b) => parseInt(a.timestamp) - parseInt(b.timestamp)
        );
        return returnResults(ascTimestamp);
      }
      case priorities === 'desc' && orderBy === 'none': {
        const highArr = records.filter((el) => el.priority === 1);
        if (highArr.length === 0) passed = false;
        let reordered = [...highArr];
        const lowArr = records.filter((el) => el.priority === 0);
        if (lowArr.length === 0) passed = false;
        reordered = [...reordered, ...lowArr];
        return returnResults(reordered);
      }
      case priorities === 'asc' && orderBy === 'none': {
        const lowArr = records.filter((el) => el.priority === 0);
        if (lowArr.length === 0) passed = false;
        let reordered = [...lowArr];
        const highArr = records.filter((el) => el.priority === 1);
        if (highArr.length === 0) passed = false;
        reordered = [...reordered, ...highArr];
        return returnResults(reordered);
      }
      default:
        return reject(new Error('No such case!').message);
    }
  });
}

export function handleRecPrioAndTimestamps(args = {}) {
  log.info({
    message: 'start of handleRecPrioAndTimestamps()',
    tag: tags.server,
  });
  return new Promise((resolve) => {
    const { imei } = store.getState().settings.mainParameters;
    const {
      timeout = { value: 5, units: 'min' },
      serverType = 'main',
      protocol = 'AVL',
      waitForClosedLink = true,
      priorities = 'none',
      order_by = 'none',
    } = args;
    const tmo = handleTimeoutParameter(timeout);
    const eventName = protocol === 'AVL' ? 'record' : 'AIS-140';
    const collectedRecords = [];
    let isAlreadyActive = false;

    log.info({
      message: 'Checking if client is currently active',
      tag: tags.server,
    });
    if (waitForClosedLink) {
      checkClientStatus({
        serverType,
        connStatus: waitForClosedLink,
        timeout: 0,
      })
        .then(() => {
          log.info({
            message: 'Client is currently active!',
            tag: tags.server,
          });
          isAlreadyActive = true;
          return null;
        })
        .catch((err) =>
          log.info({ message: `<info>catch --> ${err}`, tag: tags.server })
        );
    }

    const handleDisconnect = () => {
      log.info({
        message: '<info>< Connection lost event >',
        tag: tags.server,
      });
      isAlreadyActive = false;
    };

    emitter[serverType].on('connection_lost', handleDisconnect);

    const removeAllListeners = () => {
      emitter[serverType].removeListener(eventName, checkOpenLink);
      emitter[serverType].removeListener('connection_lost', handleDisconnect);
    };

    const checkOpenLink = (packet) => {
      log.info({
        message: 'handleRecPrioAndTimestamps --> Recieved new record!',
        tag: tags.server,
      });
      // Check if records are from correct sender
      if (Number(packet.imei) !== Number(imei)) {
        log.info({
          message:
            'handleRecPrioAndTimestamps --> Recieved record imei dont match! ',
          tag: tags.server,
        });
        return null;
      }
      const { testsInProgress = true } = store
        ? store.getState().autoTests
        : {};
      if (!testsInProgress) {
        log.info({
          message:
            'handleRecPrioAndTimestamps --> (!testsInProgress) --> remove listeners',
          tag: tags.server,
        });
        removeAllListeners();
        clearTimeout(timer);
        return null;
      }
      if (isAlreadyActive && waitForClosedLink) {
        log.info({
          message:
            'handleRecPrioAndTimestamps --> Recieved record is already active and not closed',
          tag: tags.server,
        });
        return null;
      }
      const { records } = packet.data || {};
      for (const currentRec of records) {
        log.info({
          message: 'handleRecPrioAndTimestamps --> Add new record to results!',
          tag: tags.server,
        });
        collectedRecords.push(currentRec);
      }
      return null;
    };

    emitter[serverType].on(eventName, checkOpenLink);

    function returnResults() {
      log.info({
        message:
          'handleRecPrioAndTimestamps --> Timeout reached --> return results',
        tag: tags.server,
      });
      removeAllListeners();
      if (collectedRecords.length === 0) {
        log.info({
          message:
            'handleRecPrioAndTimestamps --> ReturnResults -> Collected no records',
          tag: tags.server,
        });
        return resolve({ result: false, collectedRecords });
      }
      // eslint-disable-next-line camelcase
      if (priorities === 'none' && order_by === 'none') {
        log.info({
          message:
            'handleRecPrioAndTimestamps --> ReturnResults -> Collected records priorityies = none',
          tag: tags.server,
        });
        return resolve({ result: true, collectedRecords });
      }
      if (
        (priorities === 'desc' && collectedRecords[0].priority === 0) ||
        (priorities === 'asc' && collectedRecords[0].priority === 1)
      ) {
        log.info({
          message: `handleRecPrioAndTimestamps --> ReturnResults -> Collected records priority = ${collectedRecords[0].priority}`,
          tag: tags.server,
        });
        return resolve({ result: false, collectedRecords });
      }
      return checkPriorities({ collectedRecords, priorities, order_by })
        .then((res) =>
          res.expectedRecords
            ? resolve(res)
            : resolve({ result: res.result, collectedRecords })
        )
        .catch(() => null);
    }

    // run result timer
    const timer = setTimeout(() => returnResults(), tmo);
  });
}

/**
 * Action "Collect And Emit Records"
 */
export function collectAndEmitRecords(args) {
  log.info({ message: 'start of collectAndEmitRecords()', tag: tags.server });
  return new Promise((resolve) => {
    const { time, serverType } = args;
    const { imei } = store.getState().settings.mainParameters;
    const timeout = handleTimeoutParameter(time);
    const actionStartTime = new Date().getTime();
    const filteredRecords = [];

    /** Timeout to collect records */
    setTimeout(() => {
      const allRecords =
        store.getState().dataServer[serverType].avlRecords[imei] || [];
      /** Filter records only wich was generated after action begins */
      allRecords.forEach((record) => {
        if (record.record.timestamp >= actionStartTime)
          filteredRecords.push(record);
      });
      /** order from oldest to newest */
      const orderedRecords = filteredRecords.sort(
        (a, b) => parseInt(a.record.timestamp) - parseInt(b.record.timestamp)
      );

      log.info({
        message: 'orderedRecords sorted by timestamp',
        tag: tags.server,
      });
      log.info({
        message: orderedRecords.map((rec) => rec.record.timestamp),
        tag: tags.server,
      });
      log.info({
        message: `Record collection finished in collectAndEmitRecords(), collected records count: ${orderedRecords.length}`,
        tag: tags.server,
      });
      emitRecords(orderedRecords);
    }, timeout);

    function emitRecords(orderedRecords) {
      if (orderedRecords.length === 0) {
        return resolve(null);
      }

      setTimeout(() => {
        const packet = { imei, data: { records: [orderedRecords[0].record] } };
        log.info({
          message: ` Emit record, timestamp: [${orderedRecords[0].record.timestamp}]`,
          tag: tags.server,
        });
        emitter[serverType].emit('emitedRecord', packet);
        log.info({
          message: 'collectAndEmitRecords() emit record',
          tag: tags.server,
        });
        emitRecords(orderedRecords.slice(1));
      }, 1000);
    }
  });
}

export const sendImeiToAllServers = (deviceImei) => {
  Object.keys(server).forEach((serverType) => {
    try {
      server[serverType].addCurrentDeviceImei(deviceImei);
    } catch (error) {
      log.info({
        message: `Unable to send imei To ${serverType} server. It might be not open. ${error.message}`,
        tag: tags.server,
      });
    }
  });
};
