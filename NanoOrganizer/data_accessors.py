#!/usr/bin/env python3
"""
Data accessor classes with lazy loading and visualization.

Contains:
- UVVisData: UV-Vis spectroscopy
- SAXSData: Small-angle X-ray scattering
- WAXSData: Wide-angle X-ray diffraction
- ImageData: Microscopy images (SEM/TEM)

All classes support:
- Lazy loading (load data only when needed)
- Data validation (check if files exist)
- Built-in visualization
"""

import numpy as np
import warnings
from pathlib import Path
from typing import List, Dict, Optional, Union, Any

from NanoOrganizer.data_links import DataLink


class UVVisData:
    """UV-Vis spectroscopy data accessor with lazy loading."""
    
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.link = DataLink(data_type="uvvis")
        self._loaded_data = None
    
    def link_data(self, csv_files: List[Union[str, Path]], 
                  time_points: Optional[List[float]] = None,
                  metadata: Optional[Dict] = None):
        """Link UV-Vis CSV files to this run."""
        self.link.file_paths = [str(Path(f).absolute()) for f in csv_files]
        
        if metadata:
            self.link.metadata.update(metadata)
        
        if time_points is not None:
            if len(time_points) != len(csv_files):
                raise ValueError(f"Number of time points ({len(time_points)}) must match "
                               f"number of CSV files ({len(csv_files)})")
            self.link.metadata['time_points'] = time_points
        
        print(f"  ✓ Linked {len(csv_files)} UV-Vis CSV files")
    
    def validate(self) -> bool:
        """Check if all linked files exist."""
        missing = self.link.validate()
        if missing:
            warnings.warn(f"Missing UV-Vis files:\n" + "\n".join(f"  - {f}" for f in missing))
            return False
        return True
    
    def load(self, force_reload: bool = False) -> Dict[str, np.ndarray]:
        """Load UV-Vis data from CSV files (lazy loading)."""
        if self._loaded_data is not None and not force_reload:
            return self._loaded_data
        
        if not self.link.file_paths:
            raise ValueError("No data files linked. Use link_data() first.")
        
        all_times = []
        all_wavelengths = []
        all_absorbance = []
        
        time_points = self.link.metadata.get('time_points')
        
        for i, fpath in enumerate(self.link.file_paths):
            fpath = Path(fpath)
            if not fpath.exists():
                warnings.warn(f"File not found: {fpath}")
                continue
            
            try:
                data = np.loadtxt(fpath, delimiter=',', skiprows=1)
                wavelengths = data[:, 0]
                absorbance = data[:, 1]
                
                # Get time point
                if time_points:
                    time = time_points[i]
                else:
                    time = self._extract_time_from_filename(fpath.name, i)
                
                times = np.full(len(wavelengths), time)
                all_times.extend(times)
                all_wavelengths.extend(wavelengths)
                all_absorbance.extend(absorbance)
                
            except Exception as e:
                warnings.warn(f"Error reading {fpath}: {e}")
                continue
        
        self._loaded_data = {
            'times': np.array(all_times),
            'wavelengths': np.array(all_wavelengths),
            'absorbance': np.array(all_absorbance)
        }
        
        print(f"  ✓ Loaded {len(self.link.file_paths)} UV-Vis spectra "
              f"({len(self._loaded_data['times'])} total data points)")
        
        return self._loaded_data
    
    def _extract_time_from_filename(self, filename: str, index: int) -> float:
        """Try to extract time from filename, otherwise use index."""
        import re
        patterns = [r't(\d+)s', r't(\d+)', r'_(\d+)s', r'_(\d+)']
        for pattern in patterns:
            match = re.search(pattern, filename)
            if match:
                return float(match.group(1))
        return float(index)
    
    def plot(self, plot_type: str = "spectrum", time_point: Optional[float] = None,
             wavelength: Optional[float] = None, ax=None, **kwargs):
        """Plot UV-Vis data."""
        data = self.load()
        
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            raise ImportError("matplotlib required for plotting. Install: pip install matplotlib")
        
        if ax is None:
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=kwargs.get('figsize', (10, 6)))
        
        if plot_type == "spectrum":
            self._plot_spectrum(data, time_point, ax, **kwargs)
        elif plot_type == "kinetics":
            self._plot_kinetics(data, wavelength, ax, **kwargs)
        elif plot_type == "heatmap":
            self._plot_heatmap(data, ax, **kwargs)
        else:
            raise ValueError(f"Unknown plot_type: {plot_type}")
        
        return ax
    
    def _plot_spectrum(self, data, time_point, ax, **kwargs):
        """Plot spectrum at a specific time point."""
        times = data['times']
        wavelengths = data['wavelengths']
        absorbance = data['absorbance']
        
        unique_times = np.unique(times)
        if time_point is None:
            time_point = unique_times[len(unique_times)//2]
        
        closest_time = unique_times[np.argmin(np.abs(unique_times - time_point))]
        mask = times == closest_time
        
        wl = wavelengths[mask]
        abs_val = absorbance[mask]
        
        ax.plot(wl, abs_val, linewidth=2, label=f't = {closest_time:.0f}s')
        ax.set_xlabel('Wavelength (nm)', fontsize=12)
        ax.set_ylabel('Absorbance (a.u.)', fontsize=12)
        ax.set_title(kwargs.get('title', f'UV-Vis Spectrum at t={closest_time:.0f}s'), fontsize=13)
        ax.legend()
        ax.grid(True, alpha=0.3)
    
    def _plot_kinetics(self, data, wavelength, ax, **kwargs):
        """Plot absorbance vs time at specific wavelength."""
        times = data['times']
        wavelengths = data['wavelengths']
        absorbance = data['absorbance']
        
        if wavelength is None:
            wavelength = 520
        
        unique_wl = np.unique(wavelengths)
        closest_wl = unique_wl[np.argmin(np.abs(unique_wl - wavelength))]
        
        unique_times = np.unique(times)
        abs_at_wl = []
        for t in unique_times:
            mask = (times == t) & (np.abs(wavelengths - closest_wl) < 1.0)
            if np.any(mask):
                abs_at_wl.append(np.mean(absorbance[mask]))
            else:
                abs_at_wl.append(np.nan)
        
        ax.plot(unique_times, abs_at_wl, 'o-', linewidth=2, markersize=6)
        ax.set_xlabel('Time (s)', fontsize=12)
        ax.set_ylabel('Absorbance (a.u.)', fontsize=12)
        ax.set_title(kwargs.get('title', f'Growth Kinetics at λ={closest_wl:.0f}nm'), fontsize=13)
        ax.grid(True, alpha=0.3)
    
    def _plot_heatmap(self, data, ax, **kwargs):
        """Plot 2D heatmap of time vs wavelength."""
        import matplotlib.pyplot as plt
        
        times = data['times']
        wavelengths = data['wavelengths']
        absorbance = data['absorbance']
        
        unique_times = np.unique(times)
        n_wl_per_time = int(len(wavelengths) / len(unique_times))
        Z = absorbance.reshape(len(unique_times), n_wl_per_time)
        wl_grid = wavelengths[:n_wl_per_time]
        
        im = ax.pcolormesh(wl_grid, unique_times, Z, shading='auto', cmap='viridis')
        ax.set_xlabel('Wavelength (nm)', fontsize=12)
        ax.set_ylabel('Time (s)', fontsize=12)
        ax.set_title(kwargs.get('title', 'UV-Vis Evolution'), fontsize=13)
        plt.colorbar(im, ax=ax, label='Absorbance (a.u.)')


class SAXSData:
    """SAXS data accessor with lazy loading."""
    
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.link = DataLink(data_type="saxs")
        self._loaded_data = None
    
    def link_data(self, csv_files: List[Union[str, Path]], 
                  time_points: Optional[List[float]] = None,
                  dtime_points: Optional[List[float]] = None,
                  temperature_points: Optional[List[float]] = None,                   
                  metadata: Optional[Dict] = None):
        """Link SAXS CSV files to this run."""
        self.link.file_paths = [str(Path(f).absolute()) for f in csv_files]
        
        if metadata:
            self.link.metadata.update(metadata)
        
        if time_points is not None:
            self.link.metadata['time_points'] = time_points
        if dtime_points is not None:
            self.link.metadata['dtime_points'] = dtime_points            
        if temperature_points is not None:
            self.link.metadata['temperature_points'] = temperature_points
 
            
        print(f"  ✓ Linked {len(csv_files)} SAXS CSV files")
    
    def validate(self) -> bool:
        """Check if all linked files exist."""
        missing = self.link.validate()
        if missing:
            warnings.warn(f"Missing SAXS files:\n" + "\n".join(f"  - {f}" for f in missing))
            return False
        return True
    
    def load(self, force_reload: bool = False, verbose=False ) -> Dict[str, np.ndarray]:
        """Load SAXS data from CSV files."""
        if self._loaded_data is not None and not force_reload:
            return self._loaded_data
        
        if not self.link.file_paths:
            raise ValueError("No data files linked. Use link_data() first.")
        
        #all_times = []
        all_q = []
        all_intensity = []
        
        time_points = self.link.metadata.get('time_points')
        dtime_points = self.link.metadata.get('dtime_points')
        temperature_points = self.link.metadata.get('temperature_points')
          
        all_times =   time_points 
        all_dtimes =   dtime_points 
        all_temperatures = temperature_points
        for i, fpath in enumerate(self.link.file_paths):
            fpath = Path(fpath)
            if not fpath.exists():
                warnings.warn(f"File not found: {fpath}")
                continue            
            try:
                data = np.loadtxt(fpath, delimiter=',', skiprows=1)
                q = data[:, 0]
                intensity = data[:, 1]                
                #time = np.array( [ time_points[i]  if time_points else float(i)  ] )      
                #times = np.full(len(q), time)
                #all_times.extend(times)
                
                #all_times.extend([time])                
                all_q.extend([q])
                all_intensity.extend([intensity])
                
            except Exception as e:
                warnings.warn(f"Error reading {fpath}: {e}")
                continue
        
        self._loaded_data = {
            'times': np.array(all_times),
            'dtimes': np.array(all_dtimes),
            'temperatures': np.array(all_temperatures),            
            'q': np.array(all_q),
            'intensity': np.array(all_intensity)
        }
        
        if verbose:
            print(f"  ✓ Loaded {len(self.link.file_paths)} SAXS profiles")
        return self._loaded_data
    
    def plot(self, plot_type: str = "profile", time_point: Optional[float] = None,  q_value: Optional[float] = None, loglog: bool = True, ax=None, **kwargs):
        """Plot SAXS data."""
        data = self.load()
        
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            raise ImportError("matplotlib required for plotting")
        
        if ax is None:
            fig, ax = plt.subplots(figsize=kwargs.get('figsize', (10, 6)))
        
        if plot_type == "profile":
            self._plot_profile(data, time_point, ax, loglog, **kwargs)
        elif plot_type == "kinetics":
            self._plot_kinetics(data, q_value, ax, **kwargs)
        elif plot_type == "heatmap":
            self._plot_heatmap(data, ax, **kwargs)
        
        return ax
    
    def _plot_profile(self, data, time_point, ax, loglog, **kwargs):
        """Plot I(q) at specific time."""
        times = data['times']
        q = data['q']
        intensity = data['intensity']
        
        unique_times = np.unique(times)
        if time_point is None:
            time_point = unique_times[len(unique_times)//2]
        
        closest_time = unique_times[np.argmin(np.abs(unique_times - time_point))]
        mask = times == closest_time
        
        q_vals = q[mask].ravel()
        I_vals = intensity[mask].ravel()
        legend = kwargs.get('legend', '')
        if loglog:
            ax.loglog(q_vals, I_vals, 'o-', linewidth=2, markersize=4, label=legend,)
        else:
            ax.plot(q_vals, I_vals, 'o-', linewidth=2, markersize=4,label=legend)
        
        ax.set_xlabel('q (1/Å)', fontsize=12)
        ax.set_ylabel('Intensity (a.u.)', fontsize=12)
        ax.set_title(kwargs.get('title', f'SAXS Profile at t={closest_time:.0f}s'), fontsize=13)
        ax.grid(True, alpha=0.3)
        if legend !='':
            legend_fontsize = kwargs.get('legend_fontsize', 8)
            ax.legend(loc='best', fontsize=legend_fontsize)
            
    
    def _plot_kinetics(self, data, q_value, ax, **kwargs):
        """Plot I(t) at specific q."""
        times = data['times']
        q = data['q']
        intensity = data['intensity']
        
        if q_value is None:
            q_value = 0.02
        
        unique_q = np.unique(q)
        closest_q = unique_q[np.argmin(np.abs(unique_q - q_value))]
        
        unique_times = np.unique(times)
        I_at_q = []
        for t in unique_times:
            mask = (times == t) & (np.abs(q - closest_q) < 0.001)
            if np.any(mask):
                I_at_q.append(np.mean(intensity[mask]))
            else:
                I_at_q.append(np.nan)
        
        ax.plot(unique_times, I_at_q, 'o-', linewidth=2, markersize=6)
        ax.set_xlabel('Time (s)', fontsize=12)
        ax.set_ylabel('Intensity (a.u.)', fontsize=12)
        ax.set_title(kwargs.get('title', f'Growth at q={closest_q:.3f} 1/Å'), fontsize=13)
        ax.grid(True, alpha=0.3)
    
    def _plot_heatmap(self, data, ax, **kwargs):
        """Plot 2D heatmap."""
        import matplotlib.pyplot as plt
        
        times = data['times']
        q = data['q']
        intensity = data['intensity']
        
        unique_times = np.unique(times)
        n_q_per_time = int(len(q) / len(unique_times))
        
        Z = intensity.reshape(len(unique_times), n_q_per_time)
        q_grid = q[:n_q_per_time]
        
        im = ax.pcolormesh(q_grid, unique_times, Z, shading='auto', cmap='viridis')
        ax.set_xlabel('q (1/Å)', fontsize=12)
        ax.set_ylabel('Time (s)', fontsize=12)
        ax.set_title(kwargs.get('title', 'SAXS Evolution'), fontsize=13)
        plt.colorbar(im, ax=ax, label='Intensity (a.u.)')


class WAXSData:
    """WAXS data accessor with lazy loading."""
    
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.link = DataLink(data_type="waxs")
        self._loaded_data = None
    
    def link_data(self, csv_files: List[Union[str, Path]], 
                  time_points: Optional[List[float]] = None,
                  metadata: Optional[Dict] = None):
        """Link WAXS CSV files to this run."""
        self.link.file_paths = [str(Path(f).absolute()) for f in csv_files]
        
        if metadata:
            self.link.metadata.update(metadata)
        
        if time_points is not None:
            self.link.metadata['time_points'] = time_points
        
        print(f"  ✓ Linked {len(csv_files)} WAXS CSV files")
    
    def validate(self) -> bool:
        """Check if all linked files exist."""
        missing = self.link.validate()
        if missing:
            warnings.warn(f"Missing WAXS files:\n" + "\n".join(f"  - {f}" for f in missing))
            return False
        return True
    
    def load(self, force_reload: bool = False) -> Dict[str, np.ndarray]:
        """Load WAXS data from CSV files."""
        if self._loaded_data is not None and not force_reload:
            return self._loaded_data
        
        if not self.link.file_paths:
            raise ValueError("No data files linked. Use link_data() first.")
        
        all_times = []
        all_two_theta = []
        all_intensity = []
        
        time_points = self.link.metadata.get('time_points')
        
        for i, fpath in enumerate(self.link.file_paths):
            fpath = Path(fpath)
            if not fpath.exists():
                warnings.warn(f"File not found: {fpath}")
                continue
            
            try:
                data = np.loadtxt(fpath, delimiter=',', skiprows=1)
                two_theta = data[:, 0]
                intensity = data[:, 1]
                
                time = time_points[i] if time_points else float(i)
                times = np.full(len(two_theta), time)
                
                all_times.extend(times)
                all_two_theta.extend(two_theta)
                all_intensity.extend(intensity)
                
            except Exception as e:
                warnings.warn(f"Error reading {fpath}: {e}")
                continue
        
        self._loaded_data = {
            'times': np.array(all_times),
            'two_theta': np.array(all_two_theta),
            'intensity': np.array(all_intensity)
        }
        
        print(f"  ✓ Loaded {len(self.link.file_paths)} WAXS patterns")
        return self._loaded_data
    
    def plot(self, plot_type: str = "pattern", time_point: Optional[float] = None,
             two_theta_value: Optional[float] = None, ax=None, **kwargs):
        """Plot WAXS data."""
        data = self.load()
        
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            raise ImportError("matplotlib required for plotting")
        
        if ax is None:
            fig, ax = plt.subplots(figsize=kwargs.get('figsize', (10, 6)))
        
        if plot_type == "pattern":
            self._plot_pattern(data, time_point, ax, **kwargs)
        elif plot_type == "kinetics":
            self._plot_kinetics(data, two_theta_value, ax, **kwargs)
        elif plot_type == "heatmap":
            self._plot_heatmap(data, ax, **kwargs)
        
        return ax
    
    def _plot_pattern(self, data, time_point, ax, **kwargs):
        """Plot diffraction pattern at specific time."""
        times = data['times']
        two_theta = data['two_theta']
        intensity = data['intensity']
        
        unique_times = np.unique(times)
        if time_point is None:
            time_point = unique_times[len(unique_times)//2]
        
        closest_time = unique_times[np.argmin(np.abs(unique_times - time_point))]
        mask = times == closest_time
        
        tt_vals = two_theta[mask]
        I_vals = intensity[mask]
        
        ax.plot(tt_vals, I_vals, linewidth=2)
        ax.set_xlabel('2θ (degrees)', fontsize=12)
        ax.set_ylabel('Intensity (a.u.)', fontsize=12)
        ax.set_title(kwargs.get('title', f'WAXS Pattern at t={closest_time:.0f}s'), fontsize=13)
        ax.grid(True, alpha=0.3)
    
    def _plot_kinetics(self, data, two_theta_value, ax, **kwargs):
        """Plot peak intensity vs time."""
        times = data['times']
        two_theta = data['two_theta']
        intensity = data['intensity']
        
        if two_theta_value is None:
            two_theta_value = 30.0
        
        unique_tt = np.unique(two_theta)
        closest_tt = unique_tt[np.argmin(np.abs(unique_tt - two_theta_value))]
        
        unique_times = np.unique(times)
        I_at_tt = []
        for t in unique_times:
            mask = (times == t) & (np.abs(two_theta - closest_tt) < 0.5)
            if np.any(mask):
                I_at_tt.append(np.mean(intensity[mask]))
            else:
                I_at_tt.append(np.nan)
        
        ax.plot(unique_times, I_at_tt, 'o-', linewidth=2, markersize=6)
        ax.set_xlabel('Time (s)', fontsize=12)
        ax.set_ylabel('Intensity (a.u.)', fontsize=12)
        ax.set_title(kwargs.get('title', f'Peak Growth at 2θ={closest_tt:.1f}°'), fontsize=13)
        ax.grid(True, alpha=0.3)
    
    def _plot_heatmap(self, data, ax, **kwargs):
        """Plot 2D heatmap."""
        import matplotlib.pyplot as plt
        
        times = data['times']
        two_theta = data['two_theta']
        intensity = data['intensity']
        
        unique_times = np.unique(times)
        n_tt_per_time = int(len(two_theta) / len(unique_times))
        
        Z = intensity.reshape(len(unique_times), n_tt_per_time)
        tt_grid = two_theta[:n_tt_per_time]
        
        im = ax.pcolormesh(tt_grid, unique_times, Z, shading='auto', cmap='viridis')
        ax.set_xlabel('2θ (degrees)', fontsize=12)
        ax.set_ylabel('Time (s)', fontsize=12)
        ax.set_title(kwargs.get('title', 'WAXS Crystallization'), fontsize=13)
        plt.colorbar(im, ax=ax, label='Intensity (a.u.)')


class ImageData:
    """Microscopy image data accessor."""
    
    def __init__(self, run_id: str, data_type: str = "sem"):
        self.run_id = run_id
        self.data_type = data_type
        self.link = DataLink(data_type=data_type)
    
    def link_data(self, image_files: List[Union[str, Path]], 
                  metadata: Optional[Dict] = None):
        """Link image files to this run."""
        self.link.file_paths = [str(Path(f).absolute()) for f in image_files]
        
        if metadata:
            self.link.metadata.update(metadata)
        
        print(f"  ✓ Linked {len(image_files)} {self.data_type.upper()} images")
    
    def validate(self) -> bool:
        """Check if all linked files exist."""
        missing = self.link.validate()
        if missing:
            warnings.warn(f"Missing {self.data_type.upper()} files:\n" + 
                         "\n".join(f"  - {f}" for f in missing))
            return False
        return True
    
    def load(self, index: Optional[int] = None):
        """Load images."""
        try:
            from PIL import Image
        except ImportError:
            raise ImportError("PIL required. Install: pip install Pillow")
        
        if not self.link.file_paths:
            raise ValueError("No image files linked. Use link_data() first.")
        
        if index is not None:
            return Image.open(self.link.file_paths[index])
        else:
            return [Image.open(f) for f in self.link.file_paths]
    
    def plot(self, index: int = 0, ax=None, **kwargs):
        """Display an image."""
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            raise ImportError("matplotlib required for plotting")
        
        if ax is None:
            fig, ax = plt.subplots(figsize=kwargs.get('figsize', (8, 8)))
        
        img = self.load(index)
        ax.imshow(img, cmap='gray')
        ax.axis('off')
        
        fname = Path(self.link.file_paths[index]).name
        ax.set_title(kwargs.get('title', f'{self.data_type.upper()}: {fname}'), fontsize=13)
        
        return ax