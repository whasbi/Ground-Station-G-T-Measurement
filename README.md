# Ground Station G/T Measurement Software
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19879798.svg)](https://doi.org/10.5281/zenodo.19879798)

Developed by **Wahyudi Hasbi**  
Licensed under the **MIT License**

This repository contains a **Windows-compatible** Python/Tkinter application for satellite ground-station **G/T measurement** using Sun/cold-sky measurements and traceable solar-flux data handling.

The main application file is `GT.py`.

## Windows support

The software can run on Windows in two ways:

1. Run directly with Python: `py GT.py`
2. Build a Windows executable and run: `dist\GT.exe`

The program uses a Tkinter graphical interface. Tkinter is normally included with the official Python installer for Windows.

## Recommended Windows setup

- Windows 10 or Windows 11
- Python 3.9 or newer
- During Python installation, tick **Add python.exe to PATH**
- Internet access for Automatic NOAA/RSTN solar-flux mode
- `reportlab` for PDF export
- `pyinstaller` for building a Windows `.exe`

## Main features

- Automatic NOAA/RSTN solar-radio-flux fetch
- Manual solar-flux input for offline, laboratory, or externally documented data
- Clear warning and manual-mode fallback when internet/NOAA data are unavailable
- Manual solar-flux frequency validation using nearest bracketing frequency rules
- Automatic NOAA/RSTN bracketing-frequency selection
- F10.7 estimate modes with user confirmation and audit warnings
- Professional PDF audit report export
- In-app FAQ / Guidelines window
- Developer and MIT License notice in the software and generated PDF report

## Install dependencies on Windows

Open **Command Prompt** or **PowerShell** in the project folder and run:

    py -m pip install -r requirements.txt

If `py` is not available, use:

    python -m pip install -r requirements.txt

## Run on Windows with Python

From the project folder:

    py GT.py

or:

    python GT.py

You may also double-click `run_GT_windows.bat`.

Note: On some Windows systems, file extensions may be hidden. The launcher files should be named `run_GT_windows.bat` and `build_EXE_windows.bat`.

## Build Windows EXE

Users can create a Windows executable using **PyInstaller**.

### Easy method

Double-click `build_EXE_windows.bat`.

After the build finishes, the executable will be created here:

    dist\GT.exe

### Manual method

Run these commands from the project folder:

    py -m pip install -r requirements.txt
    py -m pip install pyinstaller
    py -m PyInstaller --onefile --windowed --name GT GT.py

The final executable will be:

    dist\GT.exe

`--windowed` is used so the GUI opens without a separate console window.

Important: Automatic NOAA/RSTN mode still requires internet access. If NOAA data cannot be reached, the software switches to **Manual solar flux input**.

## Run on Linux/macOS

From the project folder:

    python3 GT.py

Install the PDF dependency if needed:

    python3 -m pip install -r requirements.txt

## Solar flux data sources

Automatic mode uses NOAA/RSTN solar radio flux data from:

    https://services.swpc.noaa.gov/text/solar_radio_flux.txt

F10.7 estimate mode may use:

    https://services.swpc.noaa.gov/text/daily-solar-indices.txt

The software intentionally does **not** use `current-space-weather-indices.txt` for the G/T solar flux calculation path.

## Manual solar flux frequency rule

For manual solar-flux input inside the standard solar-flux frequency grid, the operating frequency must be bracketed by the **nearest lower** and **nearest upper** standard flux frequencies.

Standard solar-flux frequency grid:

    245, 410, 610, 1415, 2695, 2800, 4995, 8800, 15400 MHz

Example:

    Operating frequency = 2200 MHz
    Manual Flux Frequency 1 = 1415 MHz
    Manual Flux Frequency 2 = 2695 MHz

If the user enters a non-nearest pair, the software stops and asks the user to correct the manual input.

For operating frequencies outside the standard grid, for example above **15400 MHz**, automatic NOAA/RSTN extrapolation is stopped. The user must use **Manual solar flux input** with two traceable measured flux points that bracket the operating frequency.

For outside-grid manual input, the user is responsible for documenting:

- flux measurement source
- date/time
- calibration method
- measurement uncertainty
- frequency/flux traceability

## Network / NOAA error handling

If the internet connection fails, DNS lookup fails, or the NOAA website is unavailable, the software switches to **Manual solar flux input** and shows a readable warning instead of a raw `urlopen` error.

Use manual mode when:

- the computer is offline
- DNS/internet access is blocked
- NOAA is temporarily unavailable
- laboratory or externally documented solar-flux values are being used
- operating frequency is outside the supported standard NOAA/RSTN grid

## Data validity and recommended reporting use

For final academic or high-precision reports, prefer:

- `LIVE_NOAA_CURRENT`
- `MANUAL_DATA` with traceable documented solar-flux values

Use with caution:

- `LIVE_NOAA_OTHER_RSTN_CURRENT`

Treat the following as estimate-only unless explicitly approved:

- `PREVIOUS_NOAA_DATA_ESTIMATE`
- `F107_SCALED_NOAA_ESTIMATE`
- `F107_ONLY_MODEL_ESTIMATE`

## Repository structure

    Ground-Station-G-T-Measurement/
    ├── GT.py
    ├── README.md
    ├── LICENSE
    ├── requirements.txt
    ├── run_GT_windows.bat
    ├── build_EXE_windows.bat
    └── .gitignore

## License

This project is licensed under the MIT License. See `LICENSE`.

## Credit

If you use, modify, or redistribute this software, keep the credit and license notice:

    Developed by Wahyudi Hasbi | Licensed under the MIT License

## Citation

If you use this software in academic work, reports, or publications, please cite:

Wahyudi Hasbi. (2026). Ground Station G/T Measurement. Zenodo. https://doi.org/10.5281/zenodo.19879798
