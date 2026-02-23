"""
Easy Catcher - Catcher log analyzer and GPS visualizer
"""

import streamlit as st
import pandas as pd
import os
import sys
import json
import tempfile
import zipfile
import shutil
import importlib.util
from pathlib import Path

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from modules.utils import parse_log, create_map, create_timeline
    import folium
    from streamlit_folium import st_folium
    import plotly.express as px
    DEPENDENCIES_OK = True
except ImportError as e:
    DEPENDENCIES_OK = False
    IMPORT_ERROR = str(e)

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_toolkit_settings():
    config_path = os.path.join(ROOT_DIR, 'toolkit_settings.json')
    default_settings = {
        'catcher_path': os.path.join(ROOT_DIR, 'easy-catcher', 'catcher_mod', 'Catcher.exe'),
        'clg2txt_path': os.path.join(ROOT_DIR, 'easy-catcher', 'catcher_mod', 'Clg2Txt.exe'),
        'db_path': ''
    }

    if not os.path.exists(config_path):
        return default_settings

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            settings = json.load(f)
            return {
                'catcher_path': settings.get('catcher_path', default_settings['catcher_path']),
                'clg2txt_path': settings.get('clg2txt_path', default_settings['clg2txt_path']),
                'db_path': settings.get('db_path', default_settings['db_path'])
            }
    except Exception:
        return default_settings

def import_easy_catcher_processor():
    from modules.easy_catcher_adapter import process_dumps
    return process_dumps

def store_parsed_data(data_points, events, structured_logs, file_name):
    st.session_state['data_points'] = data_points
    st.session_state['events'] = events
    st.session_state['structured_logs'] = structured_logs
    st.session_state['file_name'] = file_name

def parse_content_and_store(content, file_name):
    data_points, events, structured_logs = parse_log(content)
    store_parsed_data(data_points, events, structured_logs, file_name)
    return data_points, events, structured_logs

EASY_CATCHER_OK = False
PROCESS_DUMPS = None
EASY_CATCHER_IMPORT_ERROR = ""

try:
    PROCESS_DUMPS = import_easy_catcher_processor()
    EASY_CATCHER_OK = True
except Exception as e:
    EASY_CATCHER_IMPORT_ERROR = str(e)

# Page config
st.set_page_config(
    page_title="Easy Catcher",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Easy Catcher")
st.markdown("Catcher log analyzer with GPS visualization and event timeline")

# Check dependencies
if not DEPENDENCIES_OK:
    st.error(f"""
    ❌ **Missing dependencies!**
    
    Error: {IMPORT_ERROR}
    
    Please install required packages:
    ```
    pip install folium streamlit-folium plotly pandas
    ```
    """)
    st.stop()

# Sidebar
with st.sidebar:
    st.header("⚙️ Settings")
    
    st.subheader("Map Options")
    auto_play = st.checkbox("Auto-play timeline", value=False)
    show_path = st.checkbox("Show full path", value=True)
    
    st.divider()
    
    st.subheader("Event Filters")
    show_ignition = st.checkbox("Ignition events", value=True)
    show_gps = st.checkbox("GPS events", value=True)
    show_movement = st.checkbox("Movement events", value=True)
    show_sleep = st.checkbox("Sleep events", value=True)
    
    st.divider()
    
    st.subheader("ℹ️ About")
    st.write("""
    This tool parses Catcher device logs to:
    - Extract GPS coordinates
    - Visualize route on map
    - Display event timeline
    - Analyze device behavior
    """)

# Main tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📁 Upload Log",
    "🗺️ Map View",
    "📈 Timeline",
    "📋 Events Table",
    "📝 Raw Log Viewer"
])

# Tab 1: Upload
with tab1:
    st.header("Upload Catcher Log File")
    
    uploaded_file = st.file_uploader(
        "Choose a Catcher .log/.txt file or a .zip containing .dmp files",
        type=['log', 'txt', 'zip'],
        help="Upload a plain log file, or a ZIP archive with dump files for Easy Catcher processing"
    )
    
    if uploaded_file:
        st.success(f"✅ File uploaded: {uploaded_file.name} ({uploaded_file.size:,} bytes)")
        
        is_zip_upload = uploaded_file.name.lower().endswith('.zip')
        parse_button_label = "🗜️ Process ZIP" if is_zip_upload else "🔍 Parse Log"

        if st.button(parse_button_label, type="primary", use_container_width=True):
            with st.spinner("Parsing log file..."):
                try:
                    if not is_zip_upload:
                        content = uploaded_file.read().decode('utf-8', errors='ignore')
                        data_points, events, structured_logs = parse_content_and_store(content, uploaded_file.name)
                    else:
                        if not EASY_CATCHER_OK:
                            st.error(
                                f"❌ Easy Catcher dump processor is unavailable: {EASY_CATCHER_IMPORT_ERROR}"
                            )
                            st.stop()

                        previous_temp_root = st.session_state.get('easy_catcher_temp_root')
                        if previous_temp_root and os.path.exists(previous_temp_root):
                            shutil.rmtree(previous_temp_root, ignore_errors=True)

                        temp_root = tempfile.mkdtemp(prefix='easy_catcher_')
                        extract_root = os.path.join(temp_root, 'extracted')
                        process_root = os.path.join(temp_root, 'process_input')
                        os.makedirs(extract_root, exist_ok=True)
                        os.makedirs(process_root, exist_ok=True)

                        zip_path = os.path.join(temp_root, uploaded_file.name)
                        with open(zip_path, 'wb') as zip_out:
                            zip_out.write(uploaded_file.getvalue())

                        with zipfile.ZipFile(zip_path, 'r') as archive:
                            for member in archive.infolist():
                                member_path = Path(member.filename)
                                if member.is_dir():
                                    continue
                                if member_path.is_absolute() or '..' in member_path.parts:
                                    continue
                                archive.extract(member, extract_root)

                        dmp_files = []
                        for root, _, files in os.walk(extract_root):
                            for file_name in files:
                                if file_name.lower().endswith('.dmp'):
                                    dmp_files.append(os.path.join(root, file_name))

                        if not dmp_files:
                            shutil.rmtree(temp_root, ignore_errors=True)
                            st.error("❌ No .dmp files were found in the ZIP archive.")
                            st.stop()

                        for index, dmp_file in enumerate(sorted(dmp_files), 1):
                            destination_name = f"{index:04d}_{os.path.basename(dmp_file)}"
                            shutil.copy2(dmp_file, os.path.join(process_root, destination_name))

                        toolkit_settings = load_toolkit_settings()
                        tool_paths = {
                            'CATCHER_EXE': toolkit_settings['catcher_path'],
                            'CLG2TXT_EXE': toolkit_settings['clg2txt_path'],
                            'DB_PATH': toolkit_settings['db_path']
                        }

                        process_logs = []

                        def _log_cb(message):
                            process_logs.append(str(message))

                        output_log_path = PROCESS_DUMPS(process_root, tool_paths, log_cb=_log_cb)

                        if not output_log_path or not os.path.exists(output_log_path):
                            st.session_state['easy_catcher_process_logs'] = process_logs
                            st.session_state['easy_catcher_temp_root'] = temp_root
                            st.session_state['easy_catcher_work_dir'] = process_root
                            st.error("❌ Failed to process ZIP dumps into a readable log.")
                            with st.expander("Easy Catcher processing log"):
                                st.code('\n'.join(process_logs) if process_logs else "No processing output available")
                            st.stop()

                        with open(output_log_path, 'rb') as processed_log:
                            processed_content = processed_log.read().decode('utf-8', errors='ignore')

                        parsed_file_name = f"{uploaded_file.name} -> {os.path.basename(output_log_path)}"
                        data_points, events, structured_logs = parse_content_and_store(processed_content, parsed_file_name)
                        st.session_state['easy_catcher_process_logs'] = process_logs
                        st.session_state['easy_catcher_temp_root'] = temp_root
                        st.session_state['easy_catcher_work_dir'] = process_root
                        st.session_state['easy_catcher_output_log'] = output_log_path
                    
                    # Display summary
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("GPS Points", len(data_points))
                    with col2:
                        st.metric("Events", len(events))
                    with col3:
                        st.metric("Log Lines", len(structured_logs))

                    if is_zip_upload and st.session_state.get('easy_catcher_work_dir'):
                        st.caption(f"Easy Catcher working folder: {st.session_state['easy_catcher_work_dir']}")
                        if st.button("📂 Open Easy Catcher Folder", use_container_width=True):
                            try:
                                os.startfile(st.session_state['easy_catcher_work_dir'])
                            except Exception as open_error:
                                st.warning(f"Could not open folder: {open_error}")

                        with st.expander("Easy Catcher processing log"):
                            logs_to_show = st.session_state.get('easy_catcher_process_logs', [])
                            st.code('\n'.join(logs_to_show) if logs_to_show else "No processing output available")
                    
                    st.success("✅ Parsing complete! Check other tabs for visualizations.")
                    
                except Exception as e:
                    st.error(f"❌ Error parsing log: {e}")
                    import traceback
                    with st.expander("Show error details"):
                        st.code(traceback.format_exc())
    else:
        st.info("👆 Upload a Catcher log file to get started")

# Tab 2: Map View
with tab2:
    st.header("🗺️ GPS Route Visualization")
    
    if 'data_points' in st.session_state:
        data_points = st.session_state.get('data_points') or []
        source_name = st.session_state.get('file_name', 'log file')
        
        if not data_points:
            st.info(f"📄 Parsed **{source_name}**, but no GPS points were found in the log.")
            st.caption("The file is loaded; map view needs NMEA/GPS position entries to render a route.")
        else:
            st.write(f"Displaying {len(data_points)} GPS points from **{source_name}**")
        
            try:
                # Create map
                map_obj = create_map(data_points)
                
                if map_obj:
                    # Display map
                    st_folium(map_obj, width=None, height=600)
                    
                    # Statistics
                    st.divider()
                    st.subheader("Route Statistics")
                    
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.metric("Total Points", len(data_points))
                    
                    with col2:
                        speeds = [p['speed'] for p in data_points if p['speed'] > 0]
                        avg_speed = sum(speeds) / len(speeds) if speeds else 0
                        st.metric("Avg Speed", f"{avg_speed:.1f} km/h")
                    
                    with col3:
                        max_speed = max([p['speed'] for p in data_points])
                        st.metric("Max Speed", f"{max_speed:.1f} km/h")
                    
                    with col4:
                        moving = sum(1 for p in data_points if p['speed'] > 5)
                        st.metric("Moving Points", f"{moving}/{len(data_points)}")
                else:
                    st.warning("Could not generate map from data")
                    
            except Exception as e:
                st.error(f"Error creating map: {e}")
                with st.expander("Show error details"):
                    import traceback
                    st.code(traceback.format_exc())
    else:
        st.info("📁 No data loaded. Upload and parse a log file first.")

# Tab 3: Timeline
with tab3:
    st.header("📈 Event Timeline")
    
    if 'events' in st.session_state and st.session_state['events']:
        events = st.session_state['events']
        
        # Filter events based on sidebar checkboxes
        filtered_events = []
        for event in events:
            event_type = event.get('Type', '')
            if (event_type == 'Ignition' and show_ignition) or \
               (event_type == 'GPS State' and show_gps) or \
               (event_type == 'Movement' and show_movement) or \
               (event_type == 'Sleep Mode' and show_sleep) or \
               event_type not in ['Ignition', 'GPS State', 'Movement', 'Sleep Mode']:
                filtered_events.append(event)
        
        st.write(f"Showing {len(filtered_events)} of {len(events)} events")
        
        try:
            # Create timeline
            fig = create_timeline(filtered_events)
            
            if fig:
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("No timeline data available")
                
        except Exception as e:
            st.error(f"Error creating timeline: {e}")
            with st.expander("Show error details"):
                import traceback
                st.code(traceback.format_exc())
    else:
        st.info("📁 No events loaded. Upload and parse a log file first.")

# Tab 4: Events Table
with tab4:
    st.header("📋 Events Table")
    
    if 'events' in st.session_state and st.session_state['events']:
        events = st.session_state['events']
        
        # Create DataFrame
        df_events = pd.DataFrame(events)
        
        # Add search/filter
        search_term = st.text_input("🔍 Search events", placeholder="Search in events...")
        
        if search_term:
            # Filter DataFrame
            mask = df_events.astype(str).apply(lambda row: row.str.contains(search_term, case=False, na=False).any(), axis=1)
            df_filtered = df_events[mask]
            st.write(f"Found {len(df_filtered)} matching events")
        else:
            df_filtered = df_events
        
        # Display table
        st.dataframe(
            df_filtered,
            use_container_width=True,
            height=600,
            column_config={
                "Timestamp": st.column_config.TextColumn("Timestamp", width="medium"),
                "Type": st.column_config.TextColumn("Type", width="small"),
                "Value": st.column_config.TextColumn("Value", width="small"),
                "Details": st.column_config.TextColumn("Details", width="large")
            }
        )
        
        # Download button
        csv = df_filtered.to_csv(index=False)
        st.download_button(
            label="💾 Download Events CSV",
            data=csv,
            file_name=f"events_{st.session_state.get('file_name', 'export')}.csv",
            mime="text/csv",
            use_container_width=True
        )
        
    else:
        st.info("📁 No events loaded. Upload and parse a log file first.")

# Tab 5: Raw Log Viewer
with tab5:
    st.header("📝 Raw Log Viewer")
    
    if 'structured_logs' in st.session_state and st.session_state['structured_logs']:
        logs = st.session_state['structured_logs']
        
        st.write(f"Total log lines: {len(logs)}")
        
        # Create DataFrame
        df_logs = pd.DataFrame(logs)
        
        # Filter controls
        col1, col2 = st.columns(2)
        
        with col1:
            # Module filter
            all_modules = sorted(set(df_logs['Module'].dropna()))
            if all_modules:
                selected_modules = st.multiselect(
                    "Filter by Module",
                    options=all_modules,
                    default=[]
                )
                if selected_modules:
                    df_logs = df_logs[df_logs['Module'].isin(selected_modules)]
        
        with col2:
            # Type filter
            all_types = sorted(set(df_logs['Type'].dropna()))
            if all_types:
                selected_types = st.multiselect(
                    "Filter by Type",
                    options=all_types,
                    default=[]
                )
                if selected_types:
                    df_logs = df_logs[df_logs['Type'].isin(selected_types)]
        
        # Search
        search_log = st.text_input("🔍 Search log content", placeholder="Search in messages...")
        
        if search_log:
            mask = df_logs['Message'].astype(str).str.contains(search_log, case=False, na=False)
            df_logs = df_logs[mask]
            st.write(f"Found {len(df_logs)} matching lines")
        
        # Display table
        st.dataframe(
            df_logs,
            use_container_width=True,
            height=600,
            column_config={
                "Line": st.column_config.NumberColumn("Line", width="small"),
                "Time": st.column_config.TextColumn("Time", width="small"),
                "Type": st.column_config.TextColumn("Type", width="small"),
                "Module": st.column_config.TextColumn("Module", width="small"),
                "Level": st.column_config.TextColumn("Level", width="small"),
                "Message": st.column_config.TextColumn("Message", width="large")
            }
        )
        
    else:
        st.info("📁 No log data loaded. Upload and parse a log file first.")

# Footer info
st.divider()
with st.expander("📖 How to use Easy Catcher"):
    st.markdown("""
    ### Quick Start Guide
    
    1. **Upload Log**: Go to the "Upload Log" tab and select a Catcher .log file
    2. **Parse**: Click "Parse Log" to analyze the file
    3. **Explore**: Use the other tabs to view different visualizations:
       - **Map View**: See the GPS route with color-coded vehicle states
       - **Timeline**: Interactive event timeline showing device behavior
       - **Events Table**: Searchable table of all detected events
       - **Raw Log**: Full log viewer with filtering options
    
    ### Event Types
    
    - **Ignition**: Engine ON/OFF events
    - **GPS State**: GPS fix status changes and no-fix reasons
    - **Movement**: Vehicle movement detection
    - **Sleep Mode**: Device sleep/wake events
    - **Trip Status**: Trip start/end and periodic info
    
    ### Map Legend
    
    - 🟢 **Green**: Moving (>5 km/h)
    - 🟠 **Orange**: Idling (Ignition ON, low speed)
    - ⚫ **Black**: Parked (Ignition OFF)
    """)
