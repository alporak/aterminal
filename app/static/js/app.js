/* ================================================================
   Alps Toolkit – Entry Point
   Imports all plugin modules and boots the application.
   ================================================================ */
import { boot } from "./core.js";
import "./gps.js";
import "./logs.js";
import "./com.js";
import "./jira.js";
import "./release.js";
import "./universal_tester_tool.js";

document.addEventListener("DOMContentLoaded", boot);

