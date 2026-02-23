"""
AT Command Parser - Extract modem commands from device logs
"""

import streamlit as st
import re
import os
import sys

# Page config
st.set_page_config(
    page_title="AT Command Parser",
    page_icon="📟",
    layout="wide"
)

st.title("📟 AT Command Parser")
st.markdown("Extract and analyze modem AT commands from device logs")

# Configuration
ALLOWED_TAGS = {
    "ATCMD",
    "MDM.QTL",
    "AT.RSP",
    "MODEM",
    "MODEM.ST",
    "MODEM.ACTION"
}

# Sidebar - Tag Selection
with st.sidebar:
    st.header("⚙️ Filter Settings")
    
    st.subheader("Select Tags to Extract")
    selected_tags = {}
    for tag in sorted(ALLOWED_TAGS):
        selected_tags[tag] = st.checkbox(tag, value=True)
    
    active_tags = {tag for tag, selected in selected_tags.items() if selected}
    
    st.divider()
    st.metric("Active Tags", len(active_tags))
    
    if st.button("🔄 Select All", use_container_width=True):
        st.rerun()

# Main area
tab1, tab2 = st.tabs(["📁 Upload Files", "📋 Parsed Output"])

with tab1:
    st.header("Upload Log Files")
    
    uploaded_files = st.file_uploader(
        "Choose .log files",
        type=['log', 'txt'],
        accept_multiple_files=True,
        help="Upload one or more device log files"
    )
    
    if uploaded_files:
        st.success(f"✅ {len(uploaded_files)} file(s) uploaded")
        
        # Display file info
        st.subheader("Uploaded Files:")
        for file in uploaded_files:
            st.write(f"- {file.name} ({file.size:,} bytes)")
        
        if st.button("🔍 Parse Logs", type="primary", use_container_width=True):
            with st.spinner("Parsing logs..."):
                # Parse all files
                all_results = []
                
                for uploaded_file in uploaded_files:
                    st.write(f"**Processing: {uploaded_file.name}**")
                    
                    try:
                        # Read file content
                        content = uploaded_file.read().decode('utf-8', errors='ignore')
                        lines = content.splitlines()
                        
                        # Regex to capture TAG and MESSAGE
                        regex_pattern = re.compile(r"-\[(.*?)\]\s+(.*)")
                        
                        file_results = []
                        for line in lines:
                            match = regex_pattern.search(line)
                            if match:
                                tag = match.group(1)
                                msg = match.group(2)
                                
                                # Filter by selected tags
                                if tag in active_tags:
                                    file_results.append({
                                        'file': uploaded_file.name,
                                        'tag': tag,
                                        'message': msg
                                    })
                        
                        all_results.extend(file_results)
                        st.write(f"  → Found {len(file_results)} matching lines")
                        
                    except Exception as e:
                        st.error(f"Error reading {uploaded_file.name}: {e}")
                
                # Store results in session state
                st.session_state['parsed_results'] = all_results
                st.success(f"✅ Parsing complete! Found {len(all_results)} total lines")
    else:
        st.info("👆 Upload log files to get started")

with tab2:
    st.header("Parsed Output")
    
    if 'parsed_results' in st.session_state and st.session_state['parsed_results']:
        results = st.session_state['parsed_results']
        
        # Statistics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Lines", len(results))
        with col2:
            unique_tags = len(set(r['tag'] for r in results))
            st.metric("Unique Tags", unique_tags)
        with col3:
            unique_files = len(set(r['file'] for r in results))
            st.metric("Files Processed", unique_files)
        
        st.divider()
        
        # Filter by tag
        available_tags = sorted(set(r['tag'] for r in results))
        tag_filter = st.multiselect(
            "Filter by Tag",
            options=available_tags,
            default=available_tags
        )
        
        # Filter results
        filtered_results = [r for r in results if r['tag'] in tag_filter]
        
        st.write(f"Showing {len(filtered_results)} of {len(results)} lines")
        
        # Display options
        show_file = st.checkbox("Show source file", value=False)
        
        # Display results
        st.subheader("Extracted Commands")
        
        # Create code block content
        output_lines = []
        for r in filtered_results:
            if show_file:
                output_lines.append(f"[{r['file']}] [{r['tag']}] {r['message']}")
            else:
                output_lines.append(f"[{r['tag']}] {r['message']}")
        
        output_text = "\n".join(output_lines)
        
        # Display in scrollable code block
        st.code(output_text, language=None, line_numbers=False)
        
        # Download button
        st.download_button(
            label="💾 Download Results",
            data=output_text,
            file_name="atcmd_parsed_output.txt",
            mime="text/plain",
            use_container_width=True
        )
        
    else:
        st.info("📁 No parsed data yet. Upload and parse log files in the 'Upload Files' tab.")

# Sidebar info
with st.sidebar:
    st.divider()
    st.subheader("ℹ️ About")
    st.write("""
    This tool extracts AT commands and modem communication from device logs.
    
    **Supported Tags:**
    - ATCMD: AT commands
    - MDM.QTL: Qualcomm modem
    - AT.RSP: AT responses
    - MODEM: General modem logs
    - MODEM.ST: Modem state
    - MODEM.ACTION: Modem actions
    """)
