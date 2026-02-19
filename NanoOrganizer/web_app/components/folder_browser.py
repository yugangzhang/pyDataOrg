#!/usr/bin/env python3
"""
Interactive Folder Browser Component for Streamlit

Provides a visual folder navigation interface without text input.
"""

import streamlit as st
from pathlib import Path
from .security import (
    format_allowed_roots,
    get_allowed_roots,
    initialize_security_context,
    is_path_allowed as security_is_path_allowed,
    is_restricted_mode,
)


def filter_file_list(file_list, and_list=[], or_list=[], no_list=[]):
    """
    Filter file list based on string patterns in filenames.

    Parameters
    ----------
    file_list : list of Path or str
        List of files to filter
    and_list : list of str
        Only return files containing ALL strings in this list
    or_list : list of str
        Only return files containing AT LEAST ONE string in this list
    no_list : list of str
        Only return files NOT containing any strings in this list

    Returns
    -------
    list
        Filtered file list
    """
    filtered = []
    n_or = len(or_list)

    for file in file_list:
        filename = str(file.name) if isinstance(file, Path) else str(file)
        flag = 1

        # Check AND conditions - must contain ALL
        if len(and_list):
            for pattern in and_list:
                if pattern not in filename:
                    flag *= 0

        # Check OR conditions - must contain AT LEAST ONE
        if len(or_list):
            count = 0
            for pattern in or_list:
                if pattern not in filename:
                    count += 1
            if count == n_or:  # None of the OR patterns matched
                flag *= 0

        # Check NO conditions - must NOT contain ANY
        if len(no_list):
            for pattern in no_list:
                if pattern in filename:
                    flag *= 0

        if flag:
            filtered.append(file)

    return filtered


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

    initialize_security_context()
    secure_restriction = is_restricted_mode()
    secure_roots = get_allowed_roots() if secure_restriction else []

    # Initialize session state
    if f'{key}_current_path' not in st.session_state:
        if initial_path:
            st.session_state[f'{key}_current_path'] = str(Path(initial_path).resolve())
        elif secure_roots:
            st.session_state[f'{key}_current_path'] = str(secure_roots[0])
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
        if secure_restriction:
            return security_is_path_allowed(path)
        if not restrict_to_start_dir:
            return True
        try:
            # Check if path is within or equal to base_path
            path.resolve().relative_to(base_path.resolve())
            return True
        except ValueError:
            return False

    if not is_path_allowed(current_path):
        if secure_roots:
            st.session_state[f'{key}_current_path'] = str(secure_roots[0])
        else:
            st.session_state[f'{key}_current_path'] = str(base_path)
        current_path = Path(st.session_state[f'{key}_current_path'])

    # Drop stale selections that are now outside allowed roots.
    st.session_state[f'{key}_selected_files'] = [
        path for path in st.session_state[f'{key}_selected_files']
        if is_path_allowed(path)
    ]

    # -------------------------------------------------------------------------
    # Quick shortcuts
    # -------------------------------------------------------------------------
    st.markdown("**📍 Quick Shortcuts:**")

    if secure_restriction:
        st.info(f"🔒 Restricted mode: Allowed folders -> {format_allowed_roots()}")
        col1, col2, col3 = st.columns(3)
    elif restrict_to_start_dir:
        st.info("🔒 Restricted mode: Can only browse current folder and subfolders")
        col1, col2, col3 = st.columns(3)
    else:
        col1, col2, col3, col4 = st.columns(4)

    if secure_restriction:
        with col1:
            if secure_roots and st.button("💼 Start", key=f"{key}_start_root"):
                st.session_state[f'{key}_current_path'] = str(secure_roots[0])
                st.rerun()
        with col2:
            alternate_root = None
            home_dir = Path.home().resolve()
            for root in secure_roots:
                if root == home_dir:
                    alternate_root = root
                    break
            if alternate_root is None and len(secure_roots) > 1:
                alternate_root = secure_roots[1]
            if alternate_root and st.button("🏠 Home", key=f"{key}_home_root"):
                st.session_state[f'{key}_current_path'] = str(alternate_root)
                st.rerun()
    elif not restrict_to_start_dir:
        with col1:
            if st.button("🏠 Home", key=f"{key}_home"):
                st.session_state[f'{key}_current_path'] = str(Path.home())
                st.rerun()

        with col2:
            if st.button("💼 CWD", key=f"{key}_cwd"):
                st.session_state[f'{key}_current_path'] = str(Path.cwd())
                st.rerun()

    if not secure_restriction:
        with col3:
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

    with (col3 if secure_restriction else (col2 if restrict_to_start_dir else col4)):
        if st.button("⬆️ Parent", key=f"{key}_parent"):
            parent = current_path.parent
            if parent != current_path:  # Not at root
                if is_path_allowed(parent):
                    st.session_state[f'{key}_current_path'] = str(parent)
                    st.rerun()
                else:
                    st.warning("🔒 Cannot navigate above allowed folders")

    st.divider()

    # -------------------------------------------------------------------------
    # Advanced File Filters
    # -------------------------------------------------------------------------
    with st.expander("🔍 Advanced Filters", expanded=False):
        st.markdown("**Filter files by name patterns:**")

        col1, col2 = st.columns(2)

        with col1:
            contains_all = st.text_input(
                "Must contain ALL (comma-separated)",
                key=f"{key}_contains_all",
                help="e.g., 'data, 2024' → only files with both 'data' AND '2024'"
            )

            contains_any = st.text_input(
                "Must contain ANY (comma-separated)",
                key=f"{key}_contains_any",
                help="e.g., 'sample1, sample2' → files with 'sample1' OR 'sample2'"
            )

        with col2:
            not_contains = st.text_input(
                "Must NOT contain (comma-separated)",
                key=f"{key}_not_contains",
                help="e.g., 'temp, backup' → exclude files with 'temp' or 'backup'"
            )

            if st.button("🔄 Reset Filters", key=f"{key}_reset_filters"):
                st.session_state[f"{key}_contains_all"] = ""
                st.session_state[f"{key}_contains_any"] = ""
                st.session_state[f"{key}_not_contains"] = ""
                st.rerun()

        # Parse filter inputs
        and_list = [s.strip() for s in contains_all.split(',') if s.strip()]
        or_list = [s.strip() for s in contains_any.split(',') if s.strip()]
        no_list = [s.strip() for s in not_contains.split(',') if s.strip()]

        # Show active filters
        if and_list or or_list or no_list:
            st.markdown("**Active filters:**")
            if and_list:
                st.info(f"✅ Must contain ALL: {', '.join(and_list)}")
            if or_list:
                st.info(f"🔵 Must contain ANY: {', '.join(or_list)}")
            if no_list:
                st.warning(f"❌ Must NOT contain: {', '.join(no_list)}")

    st.divider()

    # -------------------------------------------------------------------------
    # Breadcrumb navigation (collapsible)
    # -------------------------------------------------------------------------
    with st.expander("📂 Current Path", expanded=True):
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
                    if is_path_allowed(new_path):
                        st.session_state[f'{key}_current_path'] = str(new_path)
                        st.rerun()
                    else:
                        st.warning("🔒 That folder is outside the allowed area")

        # Show full path as text (copyable)
        st.code(str(current_path), language="bash")

    st.divider()

    # -------------------------------------------------------------------------
    # Directory contents (with scrollable container)
    # -------------------------------------------------------------------------

    try:
        # Get subdirectories
        subdirs = sorted([
            d for d in current_path.iterdir()
            if d.is_dir() and not d.name.startswith('.') and is_path_allowed(d)
        ])

        # Get files matching pattern
        if show_files:
            files = sorted([
                f for f in current_path.glob(file_pattern)
                if f.is_file() and is_path_allowed(f)
            ])

            # Apply advanced filters
            if and_list or or_list or no_list:
                files_before_filter = len(files)
                files = filter_file_list(files, and_list=and_list, or_list=or_list, no_list=no_list)
                files_after_filter = len(files)

                if files_before_filter != files_after_filter:
                    st.caption(f"🔍 Filtered: {files_before_filter} → {files_after_filter} files")
        else:
            files = []

        # Show content in scrollable container (max height 500px) with expander
        with st.expander("📁 Folders & Files", expanded=True):
            with st.container(height=400, border=True):
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
                    filter_desc = f"{file_pattern}"
                    if and_list or or_list or no_list:
                        filter_desc += " (with advanced filters)"
                    st.markdown(f"**📄 Files** ({len(files)} matching `{filter_desc}`):")

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
    initialize_security_context()
    secure_restriction = is_restricted_mode()
    secure_roots = get_allowed_roots() if secure_restriction else []

    if f'{key}_current_path' not in st.session_state:
        st.session_state[f'{key}_current_path'] = str(
            secure_roots[0] if secure_roots else Path.cwd()
        )

    current_path = Path(st.session_state[f'{key}_current_path'])

    def is_path_allowed(path):
        if secure_restriction:
            return security_is_path_allowed(path)
        return True

    if not is_path_allowed(current_path):
        if secure_roots:
            st.session_state[f'{key}_current_path'] = str(secure_roots[0])
        else:
            st.session_state[f'{key}_current_path'] = str(Path.cwd())
        current_path = Path(st.session_state[f'{key}_current_path'])

    st.markdown("**📂 Navigate to folder:**")

    # Quick shortcuts
    if secure_restriction:
        st.info(f"🔒 Restricted mode: Allowed folders -> {format_allowed_roots()}")
        col1, col2, col3 = st.columns(3)
        with col1:
            if secure_roots and st.button("💼 Start", key=f"{key}_start_root"):
                st.session_state[f'{key}_current_path'] = str(secure_roots[0])
                st.rerun()
        with col2:
            alternate_root = None
            home_dir = Path.home().resolve()
            for root in secure_roots:
                if root == home_dir:
                    alternate_root = root
                    break
            if alternate_root is None and len(secure_roots) > 1:
                alternate_root = secure_roots[1]
            if alternate_root and st.button("🏠 Home", key=f"{key}_home_root"):
                st.session_state[f'{key}_current_path'] = str(alternate_root)
                st.rerun()
    else:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            if st.button("🏠 Home", key=f"{key}_home"):
                st.session_state[f'{key}_current_path'] = str(Path.home())
                st.rerun()
        with col2:
            if st.button("💼 CWD", key=f"{key}_cwd"):
                st.session_state[f'{key}_current_path'] = str(Path.cwd())
                st.rerun()

    with (col1 if secure_restriction else col3):
        if st.button("🧪 TestData", key=f"{key}_testdata"):
            test_path = Path.cwd() / "TestData"
            if test_path.exists() and is_path_allowed(test_path):
                st.session_state[f'{key}_current_path'] = str(test_path)
                st.rerun()
    with (col3 if secure_restriction else col4):
        if st.button("⬆️ Parent", key=f"{key}_parent"):
            parent = current_path.parent
            if parent != current_path and is_path_allowed(parent):
                st.session_state[f'{key}_current_path'] = str(parent)
                st.rerun()

    # Current path
    st.code(str(current_path), language="bash")

    # Show subdirectories as buttons
    try:
        subdirs = sorted([
            d for d in current_path.iterdir()
            if d.is_dir() and not d.name.startswith('.') and is_path_allowed(d)
        ])

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
