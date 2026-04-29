# Ground Station G/T Measurement Software

Developed by **Wahyudi Hasbi**  
Licensed under the **MIT License**

This repository contains a **Windows-compatible** Python/Tkinter application for satellite ground-station **G/T measurement** using Sun/cold-sky measurements and traceable solar-flux data handling.

The main application file is:

```text
GT.py
```

## Windows support

The software can run on Windows in two ways:

1. Run directly with Python:

```bat
py GT.py
```

2. Build a Windows executable and run:

```text
dist\GT.exe
```

The program uses a Tkinter graphical interface. Tkinter is normally included with the official Python installer for Windows.

## Recommended Windows setup

- Windows 10 or Windows 11
- Python 3.9 or newer from the official Python website
- During Python installation, tick **Add python.exe to PATH**
- Internet access for Automatic NOAA/RSTN solar-flux mode
- `reportlab` for PDF export

## Main features

- Automatic NOAA/RSTN solar-radio-flux fetch
- Manual solar-flux input for offline, laboratory, or externally documented data
- Clear warning and manual-mode fallback when internet/NOAA data are unavailable
- F10.7 estimate modes with user confirmation and audit warnings
- Professional PDF audit report export
- In-app FAQ / Guidelines window
- Developer and MIT License notice in the software and generated PDF report

## Install dependencies on Windows

Open **Command Prompt** or **PowerShell** in the project folder and run:

```bat
py -m pip install -r requirements.txt
```

If `py` is not available, use:

```bat
python -m pip install -r requirements.txt
```

## Run on Windows with Python

From the project folder:

```bat
py GT.py
```

or:

```bat
python GT.py
```

You may also double-click:

```text
run_GT_windows.bat
```

## Build Windows EXE

Users can create a Windows executable using **PyInstaller**.

### Easy method

Double-click:

```text
build_EXE_windows.bat
```

After the build finishes, the executable will be created here:

```text
dist\GT.exe
```

### Manual method

Run these commands from the project folder:

```bat
py -m pip install -r requirements.txt
py -m pip install pyinstaller
py -m PyInstaller --onefile --windowed --name GT GT.py
```

The final executable will be:

```text
dist\GT.exe
```

`--windowed` is used so the GUI opens without a separate console window.

Important: Automatic NOAA/RSTN mode still requires internet access. If NOAA data cannot be reached, the software switches to **Manual solar flux input**.

## Run on Linux/macOS

From the project folder:

```bash
python3 GT.py
```

Install the PDF dependency if needed:

```bash
python3 -m pip install -r requirements.txt
```

## Solar flux data sources

Automatic mode uses NOAA/RSTN solar radio flux data from:

```text
https://services.swpc.noaa.gov/text/solar_radio_flux.txt
```

F10.7 estimate mode may use:

```text
https://services.swpc.noaa.gov/text/daily-solar-indices.txt
```

The software intentionally does **not** use `current-space-weather-indices.txt` for the G/T solar flux calculation path.

## Network / NOAA error handling

If the internet connection fails, DNS lookup fails, or the NOAA website is unavailable, the software switches to **Manual solar flux input** and shows a readable warning instead of a raw `urlopen` error.

Use manual mode when:

- the computer is offline,
- DNS/internet access is blocked,
- NOAA is temporarily unavailable,
- laboratory or externally documented solar-flux values are being used.

## Recommended reporting use

For final academic or high-precision reports, prefer:

- `LIVE_NOAA_CURRENT`, or
- `MANUAL_DATA` with traceable documented solar-flux values.

Treat the following as estimate-only unless explicitly approved:

- `PREVIOUS_NOAA_DATA_ESTIMATE`
- `F107_SCALED_NOAA_ESTIMATE`
- `F107_ONLY_MODEL_ESTIMATE`

## Repository structure

```text
gt-solar-flux-audit/
├── GT.py
├── README.md
├── LICENSE
├── requirements.txt
├── run_GT_windows.bat
├── build_EXE_windows.bat
├── .gitignore
└── GITHUB_UPLOAD_STEPS.md
```

## GitHub upload summary

1. Create a new GitHub repository, for example `gt-solar-flux-audit`.
2. Upload all files in this folder.
3. Confirm the main code file is named `GT.py`.
4. Keep the `LICENSE` file with the MIT License.
5. Mention in the repository description that this is a Windows-compatible G/T measurement tool.

## License

This project is licensed under the MIT License. See [`LICENSE`](LICENSE).

## Citation / credit

If you use or redistribute this software, keep the credit and license notice:

```text
Developed by Wahyudi Hasbi | Licensed under the MIT License
```
