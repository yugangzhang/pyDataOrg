#!/usr/bin/env python3
"""
Interactive Folder Browser Component for Streamlit

Provides a visual folder navigation interface without text input.
"""

import streamlit as st
from pathlib import Path
import os


def folder_browser(
    key="folder_browser",
    initial_path=None,
    show_files=True,
    file_pattern="*.*",
    multi_select=False,
    restrict_to_start_dir=False
):
    """
    Interactive folder browser with clickable navigation.

    Parameters
    ----------
    key : str
        Unique key for this browser instance
    initial_path : str or Path, optional
        Starting directory (default: current working directory)
    show_files : bool
        Whether to show files or only folders
    file_pattern : str
        File pattern to match (e.g., "*.csv")
    multi_select : bool
        Allow selecting multiple files
    restrict_to_start_dir : bool
        If True, user cannot navigate above the starting directory (for user mode)

    Returns
    -------
    selected_files : list of str
        List of selected file paths (empty if only navigating)
    """

    # Initialize session state
    if f'{key}_current_path' not in st.session_state:
        if initial_path:
            st.session_state[f'{key}_current_path'] = str(Path(initial_path).resolve())
        else:
            st.session_state[f'{key}_current_path'] = str(Path.cwd())

    # Store the restriction base path
    if f'{key}_base_path' not in st.session_state:
        st.session_state[f'{key}_base_path'] = st.session_state[f'{key}_current_path']

    if f'{key}_selected_files' not in st.session_state:
        st.session_state[f'{key}_selected_files'] = []

    current_path = Path(st.session_state[f'{key}_current_path'])
    base_path = Path(st.session_state[f'{key}_base_path'])

    # Helper function to check if path is allowed
    def is_path_allowed(path):
        if not restrict_to_start_dir:
            return True
        try:
            # Check if path is within or equal to base_path
            path.resolve().relative_to(base_path.resolve())
            return True
        except ValueError:
            return False

    # -------------------------------------------------------------------------
    # Quick shortcuts
    # -------------------------------------------------------------------------
    st.markdown("**📍 Quick Shortcuts:**")

    if restrict_to_start_dir:
        st.info("🔒 Restricted mode: Can only browse current folder and subfolders")
        col1, col2, col3 = st.columns(3)
    else:
        col1, col2, col3, col4 = st.columns(4)

    if not restrict_to_start_dir:
        with col1:
            if st.button("🏠 Home", key=f"{key}_home"):
                st.session_state[f'{key}_current_path'] = str(Path.home())
                st.rerun()

        with col2:
            if st.button("💼 CWD", key=f"{key}_cwd"):
                st.session_state[f'{key}_current_path'] = str(Path.cwd())
                st.rerun()

    with col3 if restrict_to_start_dir else col3:
        if st.button("🧪 TestData", key=f"{key}_testdata"):
            test_path = Path.cwd() / "TestData"
            if test_path.exists():
                if is_path_allowed(test_path):
                    st.session_state[f'{key}_current_path'] = str(test_path)
                    st.rerun()
                else:
                    st.warning("TestData folder outside allowed directory")
            else:
                st.warning("TestData folder not found")

    with (col2 if restrict_to_start_dir else col4):
        if st.button("⬆️ Parent", key=f"{key}_parent"):
            parent = current_path.parent
            if parent != current_path:  # Not at root
                if is_path_allowed(parent):
                    st.session_state[f'{key}_current_path'] = str(parent)
                    st.rerun()
                else:
                    st.warning("🔒 Cannot navigate above starting directory")

    st.divider()

    # -------------------------------------------------------------------------
    # Breadcrumb navigation
    # -------------------------------------------------------------------------
    st.markdown("**📂 Current Path:**")

    # Show breadcrumb as clickable parts
    parts = current_path.parts
    breadcrumb_cols = st.columns(min(len(parts), 8))

    for i, part in enumerate(parts):
        col_idx = i % len(breadcrumb_cols)
        with breadcrumb_cols[col_idx]:
            # Truncate long names
            display_name = part if len(part) <= 12 else part[:10] + "..."
            if st.button(f"{display_name}", key=f"{key}_breadcrumb_{i}"):
                # Navigate to this level
                new_path = Path(*parts[:i+1])
                st.session_state[f'{key}_current_path'] = str(new_path)
                st.rerun()

    # Show full path as text (copyable)
    st.code(str(current_path), language="bash")

    st.divider()

    # -------------------------------------------------------------------------
    # Directory contents (with scrollable container)
    # -------------------------------------------------------------------------

    try:
        # Get subdirectories
        subdirs = sorted([d for d in current_path.iterdir() if d.is_dir() and not d.name.startswith('.')])

        # Get files matching pattern
        if show_files:
            files = sorted(current_path.glob(file_pattern))
        else:
            files = []

        # Show content in scrollable container (max height 500px)
        with st.container(height=500, border=True):
            # Show subdirectories
            if subdirs:
                st.markdown("**📁 Folders:**")

                # Create grid of folder buttons (3 per row)
                n_cols = 3
                for i in range(0, len(subdirs), n_cols):
                    cols = st.columns(n_cols)
                    for j, subdir in enumerate(subdirs[i:i+n_cols]):
                        with cols[j]:
                            folder_name = subdir.name
                            if len(folder_name) > 20:
                                folder_name = folder_name[:18] + "..."

                            if st.button(f"📁 {folder_name}", key=f"{key}_dir_{i}_{j}", use_container_width=True):
                                st.session_state[f'{key}_current_path'] = str(subdir)
                                st.rerun()

            # Show files
            if show_files and files:
                st.divider()
                st.markdown(f"**📄 Files** ({len(files)} matching `{file_pattern}`):")

                if multi_select:
                    # Show checkboxes for multi-select
                    selected = []
                    for file in files:
                        file_name = file.name
                        if st.checkbox(
                            f"📄 {file_name}",
                            key=f"{key}_file_{file}",
                            value=str(file) in st.session_state[f'{key}_selected_files']
                        ):
                            selected.append(str(file))

                    st.session_state[f'{key}_selected_files'] = selected

                    # Show count
                    if selected:
                        st.success(f"✅ {len(selected)} file(s) selected")
                else:
                    # Show radio buttons for single select
                    file_names = [f.name for f in files]
                    selected_name = st.radio(
                        "Select file:",
                        file_names,
                        key=f"{key}_file_radio"
                    )

                    if selected_name:
                        selected_file = [str(f) for f in files if f.name == selected_name][0]
                        st.session_state[f'{key}_selected_files'] = [selected_file]

            elif show_files:
                st.info(f"No files matching pattern `{file_pattern}` in this directory")

    except PermissionError:
        st.error("❌ Permission denied - cannot access this directory")
        return []
    except Exception as e:
        st.error(f"❌ Error: {e}")
        return []

    return st.session_state[f'{key}_selected_files']


def folder_browser_dialog(key="folder_browser_dialog"):
    """
    Show folder browser in an expander/dialog style.

    Returns
    -------
    selected_path : str or None
        Selected folder path
    """
    if f'{key}_current_path' not in st.session_state:
        st.session_state[f'{key}_current_path'] = str(Path.cwd())

    current_path = Path(st.session_state[f'{key}_current_path'])

    st.markdown("**📂 Navigate to folder:**")

    # Quick shortcuts
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("🏠 Home", key=f"{key}_home"):
            st.session_state[f'{key}_current_path'] = str(Path.home())
            st.rerun()
    with col2:
        if st.button("💼 CWD", key=f"{key}_cwd"):
            st.session_state[f'{key}_current_path'] = str(Path.cwd())
            st.rerun()
    with col3:
        if st.button("🧪 TestData", key=f"{key}_testdata"):
            test_path = Path.cwd() / "TestData"
            if test_path.exists():
                st.session_state[f'{key}_current_path'] = str(test_path)
                st.rerun()
    with col4:
        if st.button("⬆️ Parent", key=f"{key}_parent"):
            parent = current_path.parent
            if parent != current_path:
                st.session_state[f'{key}_current_path'] = str(parent)
                st.rerun()

    # Current path
    st.code(str(current_path), language="bash")

    # Show subdirectories as buttons
    try:
        subdirs = sorted([d for d in current_path.iterdir() if d.is_dir() and not d.name.startswith('.')])

        if subdirs:
            st.markdown("**📁 Subfolders:**")
            for subdir in subdirs:
                if st.button(f"📁 {subdir.name}", key=f"{key}_subdir_{subdir}", use_container_width=True):
                    st.session_state[f'{key}_current_path'] = str(subdir)
                    st.rerun()
        else:
            st.info("No subfolders in this directory")

    except PermissionError:
        st.error("❌ Permission denied")
    except Exception as e:
        st.error(f"❌ Error: {e}")

    return str(current_path)
