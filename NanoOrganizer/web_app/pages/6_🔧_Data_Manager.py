#!/usr/bin/env python3
"""
Data Management GUI - Create and manage NanoOrganizer projects.

Launch with:
    streamlit run NanoOrganizer/web/data_manager.py

Or add to setup.py as:
    'nanoorganizer-manage=NanoOrganizer.web.data_manager_cli:main'
"""

import matplotlib
matplotlib.use("Agg")

import streamlit as st  # noqa: E402
from pathlib import Path  # noqa: E402
import json  # noqa: E402
from datetime import datetime  # noqa: E402

from NanoOrganizer import (  # noqa: E402
    DataOrganizer, RunMetadata, ReactionParams, ChemicalSpec,
    save_time_series_to_csv
)
from NanoOrganizer.core.run import DEFAULT_LOADERS  # noqa: E402

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def browse_files(base_dir, pattern="*.*"):
    """Browse directory and find files matching pattern."""
    base_path = Path(base_dir)
    if not base_path.exists():
        return []
    files = list(base_path.rglob(pattern))
    return [str(f) for f in sorted(files)]


def get_data_type_info():
    """Return information about each data type."""
    return {
        'uvvis': {
            'name': 'UV-Vis Spectroscopy',
            'pattern': '*.csv',
            'description': 'Time-series UV-Vis absorption spectra (wavelength vs absorbance)'
        },
        'saxs': {
            'name': 'SAXS 1D',
            'pattern': '*.csv',
            'description': 'Small-Angle X-ray Scattering profiles (q vs intensity)'
        },
        'waxs': {
            'name': 'WAXS 1D',
            'pattern': '*.csv',
            'description': 'Wide-Angle X-ray Scattering patterns (2θ vs intensity)'
        },
        'dls': {
            'name': 'DLS',
            'pattern': '*.csv',
        },
        'xas': {
            'name': 'XAS',
            'pattern': '*.csv',
            'description': 'X-ray Absorption Spectroscopy (energy vs absorption)'
        },
        'saxs2d': {
            'name': 'SAXS 2D',
            'pattern': '*.npy',
            'description': '2D SAXS detector images (.npy, .png, .tif)'
        },
        'waxs2d': {
            'name': 'WAXS 2D',
            'pattern': '*.npy',
            'description': '2D WAXS detector images (.npy, .png, .tif)'
        },
        'sem': {
            'name': 'SEM Images',
            'pattern': '*.png',
            'description': 'Scanning Electron Microscopy images'
        },
        'tem': {
            'name': 'TEM Images',
            'pattern': '*.png',
            'description': 'Transmission Electron Microscopy images'
        },
    }


# ---------------------------------------------------------------------------
# Session state initialization
# ---------------------------------------------------------------------------

if 'current_organizer' not in st.session_state:
    st.session_state['current_organizer'] = None

if 'current_run' not in st.session_state:
    st.session_state['current_run'] = None

if 'chemicals_list' not in st.session_state:
    st.session_state['chemicals_list'] = []

# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Data Manager", layout="wide")
st.title("🔧 NanoOrganizer Data Manager")
st.markdown("Create projects, add metadata, and link experimental data")

# ---------------------------------------------------------------------------
# Sidebar: Project Management
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("📁 Project Management")

    project_action = st.radio(
        "Action",
        ["Create New Project", "Load Existing Project"],
        help="Create a new NanoOrganizer project or load an existing one"
    )

    if project_action == "Create New Project":
        project_dir = st.text_input(
            "Project directory",
            value=str(Path.cwd() / "MyNanoProject"),
            help="Directory where project will be created"
        )

        if st.button("🆕 Create Project"):
            try:
                org = DataOrganizer(project_dir)
                st.session_state['current_organizer'] = org
                st.session_state['project_dir'] = project_dir
                st.success(f"✅ Created project at {project_dir}")
            except Exception as e:
                st.error(f"Error creating project: {e}")

    else:  # Load existing
        project_dir = st.text_input(
            "Project directory",
            value=str(Path.cwd() / "Demo"),
            help="Directory containing .metadata/ folder"
        )

        if st.button("📂 Load Project"):
            try:
                org = DataOrganizer.load(project_dir)
                st.session_state['current_organizer'] = org
                st.session_state['project_dir'] = project_dir
                st.success(f"✅ Loaded {len(org.list_runs())} run(s)")
            except Exception as e:
                st.error(f"Error loading project: {e}")

    # Show current project status
    org = st.session_state.get('current_organizer')
    if org:
        st.divider()
        st.success("✅ Project active")
        st.metric("Runs", len(org.list_runs()))

        # Quick links
        st.divider()
        st.markdown("**Quick Actions**")
        if st.button("💾 Save Project"):
            try:
                org.save()
                st.success("✅ Project saved!")
            except Exception as e:
                st.error(f"Error saving: {e}")

        if st.button("✅ Validate All Data"):
            results = org.validate_all()
            all_valid = all(all(v.values()) if isinstance(v, dict) else v
                           for v in results.values())
            if all_valid:
                st.success("✅ All data files valid!")
            else:
                st.error("❌ Some files are missing")
                st.json(results)

        # View existing runs
        if org.list_runs():
            with st.expander("📋 Existing Runs"):
                for run_key in org.list_runs():
                    st.text(run_key)

# ---------------------------------------------------------------------------
# Main Area: Run Creation/Editing
# ---------------------------------------------------------------------------

if org is None:
    st.info("👈 Create or load a project to get started")
    st.stop()

# Tab navigation
tab1, tab2, tab3 = st.tabs(["📝 Create Run", "🔗 Link Data", "📊 View Runs"])

# ---------------------------------------------------------------------------
# TAB 1: Create Run
# ---------------------------------------------------------------------------

with tab1:
    st.header("Create New Run")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Basic Information")

        project_name = st.text_input(
            "Project Name",
            value="Project_Au",
            help="High-level project identifier"
        )

        experiment_date = st.date_input(
            "Experiment Date",
            value=datetime.now(),
            help="Date of experiment"
        )
        experiment_name = st.text_input(
            "Experiment Name",
            value=experiment_date.strftime("%Y-%m-%d"),
            help="Experiment identifier (default: date)"
        )

        run_id = st.text_input(
            "Run ID",
            value="Run_001",
            help="Unique identifier for this run"
        )

        sample_id = st.text_input(
            "Sample ID",
            value="Sample_001",
            help="Sample identifier"
        )

    with col2:
        st.subheader("Reaction Parameters")

        temperature = st.number_input(
            "Temperature (°C)",
            value=80.0,
            min_value=-273.0,
            max_value=1000.0,
            step=1.0
        )

        ph = st.number_input(
            "pH",
            value=7.0,
            min_value=0.0,
            max_value=14.0,
            step=0.1
        )

        duration = st.number_input(
            "Duration (min)",
            value=60.0,
            min_value=0.0,
            step=1.0
        )

    # Chemicals section
    st.subheader("Chemicals")

    col1, col2, col3, col4 = st.columns([3, 2, 2, 1])

    with col1:
        chem_name = st.text_input("Chemical name", key="chem_name")
    with col2:
        chem_conc = st.number_input("Concentration (mM)", value=1.0, key="chem_conc")
    with col3:
        chem_volume = st.number_input("Volume (μL)", value=100.0, key="chem_volume")
    with col4:
        st.write("")  # Spacer
        st.write("")  # Spacer
        if st.button("➕ Add"):
            if chem_name:
                st.session_state['chemicals_list'].append({
                    'name': chem_name,
                    'concentration': chem_conc,
                    'volume': chem_volume
                })

    # Display chemicals list
    if st.session_state['chemicals_list']:
        st.markdown("**Added Chemicals:**")
        for idx, chem in enumerate(st.session_state['chemicals_list']):
            col1, col2 = st.columns([5, 1])
            with col1:
                st.text(f"• {chem['name']} - {chem['concentration']} mM - {chem['volume']} μL")
            with col2:
                if st.button("🗑️", key=f"del_{idx}"):
                    st.session_state['chemicals_list'].pop(idx)
                    st.rerun()

    # Tags and notes
    st.subheader("Additional Information")

    col1, col2 = st.columns(2)
    with col1:
        tags_input = st.text_input(
            "Tags (comma-separated)",
            value="gold, nanoparticle, synthesis",
            help="Tags for searching/filtering"
        )
        tags = [t.strip() for t in tags_input.split(',') if t.strip()]

    with col2:
        notes = st.text_area(
            "Notes",
            value="Experimental notes here...",
            help="Any additional notes"
        )

    # Create run button
    st.divider()
    if st.button("✨ Create Run", type="primary"):
        try:
            # Create chemical specs
            chemicals = [
                ChemicalSpec(
                    name=c['name'],
                    concentration=c['concentration'],
                    volume_uL=c['volume']
                )
                for c in st.session_state['chemicals_list']
            ]

            # Create metadata
            metadata = RunMetadata(
                project=project_name,
                experiment=experiment_name,
                run_id=run_id,
                sample_id=sample_id,
                reaction=ReactionParams(
                    chemicals=chemicals,
                    temperature_C=temperature,
                    ph=ph,
                    duration_min=duration
                ),
                tags=tags,
                notes=notes
            )

            # Create run
            run = org.create_run(metadata)
            st.session_state['current_run'] = run
            st.session_state['current_run_key'] = f"{project_name}/{experiment_name}/{run_id}"

            st.success(f"✅ Created run: {project_name}/{experiment_name}/{run_id}")
            st.info("👉 Switch to 'Link Data' tab to add experimental data")

        except Exception as e:
            st.error(f"Error creating run: {e}")

# ---------------------------------------------------------------------------
# TAB 2: Link Data
# ---------------------------------------------------------------------------

with tab2:
    st.header("Link Experimental Data")

    # Select run to link data to
    run_keys = org.list_runs()
    if not run_keys:
        st.warning("No runs available. Create a run first in the 'Create Run' tab.")
        st.stop()

    selected_run_key = st.selectbox(
        "Select Run",
        run_keys,
        index=len(run_keys) - 1,  # Default to most recent
        help="Select which run to link data to"
    )

    run = org.get_run(selected_run_key)

    # Select data type
    st.subheader("Data Type")

    data_type_info = get_data_type_info()
    data_types = list(data_type_info.keys())

    selected_dtype = st.selectbox(
        "Data type",
        data_types,
        format_func=lambda x: data_type_info[x]['name'],
        help="Select the type of data to link"
    )

    info = data_type_info[selected_dtype]
    st.info(f"ℹ️ {info['description']}")

    # File selection
    st.subheader("Select Files")

    file_source = st.radio(
        "File source",
        ["Browse server", "Enter paths manually"],
        horizontal=True
    )

    selected_files = []

    if file_source == "Browse server":
        base_dir = st.text_input(
            "Base directory",
            value=str(Path(st.session_state.get('project_dir', Path.cwd()))),
            help="Directory to search for files"
        )

        pattern = st.text_input(
            "File pattern",
            value=info['pattern'],
            help="File pattern to match (e.g., *.csv, *.npy)"
        )

        if st.button("🔍 Search Files"):
            found_files = browse_files(base_dir, pattern)
            st.session_state[f'found_files_{selected_dtype}'] = found_files

        if f'found_files_{selected_dtype}' in st.session_state:
            found_files = st.session_state[f'found_files_{selected_dtype}']
            if found_files:
                st.success(f"Found {len(found_files)} files")
                selected_files = st.multiselect(
                    "Select files to link",
                    found_files,
                    default=found_files[:5],  # Select first 5 by default
                    help="Select which files to link to this run"
                )
            else:
                st.warning("No files found matching pattern")

    else:  # Manual entry
        paths_text = st.text_area(
            "File paths (one per line)",
            value="",
            height=200,
            help="Enter file paths, one per line"
        )
        if paths_text:
            selected_files = [p.strip() for p in paths_text.split('\n') if p.strip()]

    # Additional metadata based on data type
    st.subheader("Additional Metadata")

    time_points = None
    extra_metadata = {}

    if selected_dtype in ['uvvis', 'saxs', 'waxs', 'dls', 'xas']:
        # Time-series data
        time_input = st.text_input(
            "Time points (comma-separated, seconds)",
            value="0, 30, 60, 120, 180, 300, 600",
            help="Time points corresponding to each file"
        )
        if time_input:
            time_points = [float(t.strip()) for t in time_input.split(',') if t.strip()]

    elif selected_dtype in ['saxs2d', 'waxs2d']:
        # 2D detector data needs calibration
        col1, col2, col3 = st.columns(3)
        with col1:
            pixel_size = st.number_input("Pixel size (mm)", value=0.172, format="%.4f")
        with col2:
            sdd = st.number_input("Sample-detector distance (mm)", value=3000.0)
        with col3:
            wavelength = st.number_input("Wavelength (Å)", value=1.0, format="%.4f")

        extra_metadata = {
            'pixel_size_mm': pixel_size,
            'sdd_mm': sdd,
            'wavelength_A': wavelength
        }

        # Time points for 2D data
        time_input = st.text_input(
            "Time points (comma-separated, seconds)",
            value="0, 30, 60, 120",
            help="Time points corresponding to each file"
        )
        if time_input:
            time_points = [float(t.strip()) for t in time_input.split(',') if t.strip()]

    # Link data button
    st.divider()

    if selected_files:
        st.success(f"Ready to link {len(selected_files)} files")

        if st.button(f"🔗 Link {selected_dtype.upper()} Data", type="primary"):
            try:
                loader = getattr(run, selected_dtype)

                # Prepare kwargs
                link_kwargs = {}
                if time_points:
                    link_kwargs['time_points'] = time_points
                if extra_metadata:
                    link_kwargs.update(extra_metadata)

                # Link data
                loader.link_data(selected_files, **link_kwargs)

                st.success(f"✅ Linked {len(selected_files)} {selected_dtype.upper()} files!")
                st.info("💾 Don't forget to save the project!")

            except Exception as e:
                st.error(f"Error linking data: {e}")
    else:
        st.info("Select files to link")

# ---------------------------------------------------------------------------
# TAB 3: View Runs
# ---------------------------------------------------------------------------

with tab3:
    st.header("View Existing Runs")

    run_keys = org.list_runs()
    if not run_keys:
        st.info("No runs in this project yet")
        st.stop()

    for run_key in run_keys:
        run = org.get_run(run_key)
        meta = run.metadata

        with st.expander(f"📋 {run_key}", expanded=False):
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("**Basic Info**")
                st.text(f"Project: {meta.project}")
                st.text(f"Experiment: {meta.experiment}")
                st.text(f"Run ID: {meta.run_id}")
                st.text(f"Sample ID: {meta.sample_id}")
                st.text(f"Temperature: {meta.reaction_temperature}")
                st.text(f"Tags: {meta.tags}")

            with col2:
                st.markdown("**Linked Data**")
                for attr, _, _ in DEFAULT_LOADERS:
                    loader = getattr(run, attr)
                    n_files = len(loader.link.file_paths)
                    if n_files > 0:
                        st.text(f"✅ {attr.upper()}: {n_files} files")

            st.markdown("**Chemicals**")
            if meta.reaction and meta.reaction.chemicals:
                for chem in meta.reaction.chemicals:
                    st.text(f"• {chem.name} - {chem.concentration} mM")

            st.markdown("**Notes**")
            st.text(meta.notes)

            # Delete run button
            if st.button(f"🗑️ Delete Run", key=f"delete_{run_key}"):
                if st.checkbox(f"Confirm deletion of {run_key}", key=f"confirm_{run_key}"):
                    # Note: Need to implement delete_run in DataOrganizer
                    st.warning("Delete functionality to be implemented")

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.divider()
st.markdown("""
### 💡 Workflow Tips
1. **Create Run**: Fill in metadata and create a run
2. **Link Data**: Browse/select files and link them to the run
3. **Save Project**: Save metadata to disk (`.metadata/` folder)
4. **Visualize**: Use `nanoorganizer-viz` to explore your data
""")
