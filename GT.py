"""
Satellite G/T Measurement
Windows-compatible Tkinter application.

Developed by Wahyudi Hasbi.
License: MIT License.


NOAA sources used for automatic solar radio flux:
    Primary multi-frequency source:
        https://services.swpc.noaa.gov/text/solar_radio_flux.txt
    Secondary estimate-only F10.7 source, used only when multi-frequency RSTN data
    are unavailable and the user confirms estimate mode:
        https://services.swpc.noaa.gov/text/daily-solar-indices.txt

This software intentionally does not use current-space-weather-indices.txt for G/T
solar flux calculation. That file is a broad current-indices summary and may contain
missing RSTN radio-flux placeholders. The automatic G/T path is kept traceable by
using solar_radio_flux.txt, and only uses F10.7 from daily-solar-indices.txt as a
clearly warned estimate by scaling a previous measured RSTN spectrum, or as a final last-resort F10.7-only model estimate when no measured RSTN spectrum and no manual input are available.

This version supports two transparent solar-flux modes:
    1) Automatic NOAA/RSTN fetch using the nearest usable RSTN station.
    2) Manual user-entered solar flux pairs for laboratory or offline use.

Data rule:
    - No hidden built-in fallback spectrum is used.
    - Automatic mode uses only NOAA solar_radio_flux.txt.
    - Automatic mode prefers the latest NOAA row.
    - If the latest NOAA row has no usable supported RSTN station, the software can estimate from F10.7 only after a warning and user confirmation.
    - F10.7-scaled estimate mode scales a previous measured RSTN spectrum by the ratio of current F10.7 to reference-date F10.7.
    - F10.7-only model estimate is a final last-resort option: S_model(f)=F10.7*(f/2800 MHz)^m, with user-visible assumed m.
    - Previous NOAA data and F10.7 model data are clearly labeled as ESTIMATE data; they are not recommended for final academic/high precision measurement reports.
    - All estimate modes are clearly labeled and are not recommended for final academic/high precision measurement reports.
    - If NOAA cannot be loaded or parsed, calculation stops and the user can switch to Manual solar flux input.
    - Manual input inside the standard solar-flux grid must use the nearest standard bracketing frequency pair.
    - Manual input outside the standard solar-flux grid must use two traceable measured flux points that bracket the operating frequency; the user is responsible for documenting source, date, and traceability.

Supported RSTN station columns in the NOAA product:
    Learmonth, San Vito, Sagamore Hill / Sag Hill, Palehua

Run on Windows:
    py GT.py

Optional PDF export dependency:
    py -m pip install reportlab
"""

import math
import tkinter as tk
from tkinter import messagebox, scrolledtext, filedialog
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import Table, TableStyle, SimpleDocTemplate, Paragraph, Spacer, PageBreak, KeepTogether
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib import colors
    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False


class GTStationApp:
    DEVELOPER_NAME = "Wahyudi Hasbi"
    LICENSE_NAME = "MIT License"
    LICENSE_FOOTER_TEXT = "Developed by Wahyudi Hasbi | Licensed under the MIT License"
    COPYRIGHT_TEXT = "Copyright (c) 2026 Wahyudi Hasbi"
    MIT_LICENSE_TEXT = """MIT License

Copyright (c) 2026 Wahyudi Hasbi

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the \"Software\"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE."""

    NOAA_URL = "https://services.swpc.noaa.gov/text/solar_radio_flux.txt"
    DSD_URL = "https://services.swpc.noaa.gov/text/daily-solar-indices.txt"
    PREVIOUS_NOAA_RECOMMENDED_LIMIT_DAYS = 3
    CURRENT_SPACE_WEATHER_INDICES_USED = False

    # Standard solar-flux frequency grid used to validate normal manual input
    # and to avoid unsupported automatic extrapolation. Manual mode must use
    # the two adjacent standard frequencies that bracket the operating
    # frequency when f_op is inside this grid. Example: f_op = 2200 MHz
    # requires 1415 and 2695 MHz.
    #
    # If f_op is outside this standard grid, automatic NOAA/RSTN calculation is
    # stopped and the user is directed to Manual mode. In that special case,
    # the user may enter two traceable measured solar-flux frequencies from
    # their own source, but those two frequencies must bracket f_op.
    #
    # F10.7-only model mode keeps its own internal model grid and is not
    # restricted by this manual-input validation rule.
    STANDARD_SOLAR_FLUX_FREQUENCIES_MHZ = [245.0, 410.0, 610.0, 1415.0, 2695.0, 2800.0, 4995.0, 8800.0, 15400.0]
    FREQUENCY_MATCH_TOLERANCE_MHZ = 1e-6

    # Rows that are direct inputs to the final transparent G/T equation:
    # G/T = 10 log10[(8*pi*k*(y-1))/(S_rx*1e-22*lambda^2*L)]
    # In the GUI text report these rows get a leading star.
    # In the PDF report the same row labels are bold, without a star.
    DIRECT_GT_PARAMETERS = {
        "Boltzmann Constant k",
        "y",
        "Y Factor",
        "Solar Flux at Antenna Ref. Plane",
        "Wavelength",
        "Beam Correction Factor",
    }

    # Station coordinates are fixed configuration constants used only to select
    # the nearest station by great-circle distance from the entered ground site.
    # column_index refers to NOAA solar_radio_flux.txt token positions after split().
    RSTN_STATIONS = [
        {
            "name": "Learmonth",
            "short": "Learmonth",
            "column_index": 4,
            "utc_label": "0500 UTC",
            "lat": -22.23330,
            "lon": 114.08333,
            "location": "Learmonth, Western Australia",
        },
        {
            "name": "San Vito",
            "short": "San Vito",
            "column_index": 5,
            "utc_label": "1200 UTC",
            "lat": 40.40248,
            "lon": 17.43248,
            "location": "San Vito dei Normanni, Italy",
        },
        {
            "name": "Sagamore Hill",
            "short": "Sag Hill",
            "column_index": 6,
            "utc_label": "1700 UTC",
            "lat": 42.63083,
            "lon": -70.81500,
            "location": "South Hamilton, Massachusetts, USA",
        },
        {
            "name": "Palehua",
            "short": "Palehua",
            "column_index": 9,
            "utc_label": "2300 UTC",
            "lat": 21.37914,
            "lon": -158.11412,
            "location": "Palehua, Hawaii, USA",
        },
    ]

    def __init__(self, root):
        self.root = root
        self.root.title("Ground Station G/T")
        self.root.geometry("1220x1120")
        self.root.minsize(1050, 760)

        tk.Label(
            root,
            text="G/T Measurement, RF Source: Sun - Solar Flux",
            font=("Arial", 16, "bold"),
            bg="#2b78ad",
            fg="white",
        ).pack(fill="x", pady=5)

        container = tk.Frame(root)
        container.pack(fill="x", padx=20)

        self.entries = {}
        fields = [
            ("Ground Station Latitude", "lat", "degrees", ""),
            ("Ground Station Longitude", "lon", "degrees", ""),
            ("Operating Frequency", "freq", "MHz", "8200"),
            ("Antenna HPBW", "bw", "degrees", "0.23"),
            ("P_sun", "psun", "dBm", ""),
            ("P_csky", "pcsky", "dBm", ""),
            ("Solar Elevation Angle", "el", "degrees", ""),
        ]

        for text, key, unit, default in fields:
            frame = tk.Frame(container)
            frame.pack(fill="x", pady=2)
            tk.Label(frame, text=f"{text}:", width=30, anchor="w").pack(side="left")
            entry = tk.Entry(frame, width=15)
            entry.insert(0, default)
            entry.pack(side="left", padx=5)
            tk.Label(frame, text=unit, width=10, anchor="w").pack(side="left")
            self.entries[key] = entry

        hint = (
            "Latitude range: -90 to +90. Longitude range: -180 to +180. "
            "Automatic mode selects the nearest usable RSTN station: Learmonth, San Vito, Sagamore Hill, or Palehua."
        )
        tk.Label(container, text=hint, anchor="w", fg="#555555").pack(fill="x", pady=(4, 0))

        mode_frame = tk.LabelFrame(root, text="Solar Flux Data Source", padx=10, pady=6)
        mode_frame.pack(fill="x", padx=20, pady=(8, 0))
        self.solar_mode = tk.StringVar(value="auto")
        tk.Radiobutton(
            mode_frame,
            text="Automatic NOAA/RSTN fetch",
            variable=self.solar_mode,
            value="auto",
        ).pack(side="left", padx=(0, 22))
        tk.Radiobutton(
            mode_frame,
            text="Manual solar flux input",
            variable=self.solar_mode,
            value="manual",
        ).pack(side="left")

        manual_frame = tk.LabelFrame(
            root,
            text="Manual Solar Flux Input - use when NOAA data are unavailable or when using lab-measured values",
            padx=10,
            pady=6,
        )
        manual_frame.pack(fill="x", padx=20, pady=(8, 0))
        self.manual_entries = {}
        manual_fields = [
            ("Manual Flux Frequency 1", "mf1", "MHz", "4995"),
            ("Manual Flux 1", "ms1", "SFU", ""),
            ("Manual Flux Frequency 2", "mf2", "MHz", "8800"),
            ("Manual Flux 2", "ms2", "SFU", ""),
            ("Manual Data Date/ID", "mdate", "text", "Manual input"),
            ("Manual Source Note", "mnote", "text", "User-supplied solar flux values"),
        ]
        for text, key, unit, default in manual_fields:
            frame = tk.Frame(manual_frame)
            frame.pack(side="left", padx=(0, 8), pady=2)
            tk.Label(frame, text=text, anchor="w").pack(anchor="w")
            entry = tk.Entry(frame, width=18)
            entry.insert(0, default)
            entry.pack(anchor="w")
            tk.Label(frame, text=unit, fg="#555555").pack(anchor="w")
            self.manual_entries[key] = entry

        warning_text = (
            "Data rule: no hidden fallback spectra are used. Automatic mode uses NOAA RSTN rows when available; "
            "F10.7 scaling, older NOAA rows, or F10.7-only model estimates are allowed only as clearly warned estimates. "
            "Manual mode records user-supplied flux values."
        )
        tk.Label(root, text=warning_text, anchor="w", fg="#8a4b00").pack(fill="x", padx=20, pady=(5, 0))

        f107_frame = tk.Frame(root)
        f107_frame.pack(fill="x", padx=20, pady=(5, 0))
        tk.Label(
            f107_frame,
            text="Last-resort F10.7-only spectral index m:",
            anchor="w",
        ).pack(side="left")
        self.f107_index_entry = tk.Entry(f107_frame, width=8)
        self.f107_index_entry.insert(0, "0.6")
        self.f107_index_entry.pack(side="left", padx=(5, 10))
        tk.Label(
            f107_frame,
            text="Used only if no RSTN spectrum is available and Manual mode is not selected. Estimate only.",
            anchor="w",
            fg="#8a4b00",
        ).pack(side="left")

        btn_frame = tk.Frame(root)
        btn_frame.pack(pady=15)

        tk.Button(
            btn_frame,
            text="Execute G/T Audit",
            command=self.calculate,
            bg="#1a73e8",
            fg="white",
            font=("Arial", 10, "bold"),
            width=42,
        ).pack(side="left", padx=5)

        tk.Button(
            btn_frame,
            text="Create PDF Report",
            command=self.export_pdf,
            bg="#34a853",
            fg="white",
            font=("Arial", 10, "bold"),
            width=40,
        ).pack(side="left", padx=5)

        tk.Button(
            btn_frame,
            text="FAQ / Guidelines",
            command=self.show_faq_guidelines,
            bg="#fbbc04",
            fg="black",
            font=("Arial", 10, "bold"),
            width=22,
        ).pack(side="left", padx=5)

        self.output = scrolledtext.ScrolledText(root, width=155, height=55, font=("Consolas", 10))
        self.output.pack(fill="both", expand=True, padx=20, pady=(10, 4))

        tk.Label(
            root,
            text=self.LICENSE_FOOTER_TEXT,
            anchor="center",
            fg="#666666",
            font=("Arial", 8, "italic"),
        ).pack(fill="x", padx=20, pady=(0, 6))

    def get_faq_guidelines_text(self):
        """Return user-facing FAQ and operating guidelines for the Help window."""
        return """G/T AUDIT SUITE - FAQ AND USER GUIDELINES

PURPOSE
This software calculates satellite receive-system G/T using a Sun / cold-sky measurement. It is designed for academic auditability, so the report shows data source, assumptions, constants, formulas, warnings, and direct inputs to the final equation.

SOFTWARE CREDIT AND LICENSE
Developed by Wahyudi Hasbi.
Released under the MIT License. Keep this credit and license notice in reports and redistributed copies of the software.

QUICK WORKFLOW
1. Enter the ground station latitude and longitude.
2. Enter the operating frequency in MHz and the antenna HPBW in degrees.
3. Enter measured P_sun and P_csky in dBm.
4. Enter the solar elevation angle in degrees.
5. Select the solar flux source:
   - Automatic NOAA/RSTN fetch for normal online use.
   - Manual solar flux input for laboratory, offline, or externally documented values.
6. Click Execute G/T Audit.
7. Review the Data Validity Status and Data Warning before using the result.
8. Export the PDF only after checking that the solar flux source is acceptable for your report.

FREQUENTLY ASKED QUESTIONS

Q1. What does G/T mean?
G/T is antenna gain divided by system noise temperature. It is expressed in dB/K and is a key receive-station performance metric.

Q2. What is P_sun?
P_sun is the measured receiver power while the antenna is pointed at the Sun.

Q3. What is P_csky?
P_csky is the measured receiver power while the antenna is pointed at nearby cold sky, away from the Sun and major radio sources.

Q4. Why must P_sun be greater than P_csky?
The Sun must produce a positive power increase. The software computes y = 10^((P_sun - P_csky)/10). For a physically valid Sun/cold-sky measurement, y must be greater than 1.

Q5. Which NOAA source is used for automatic solar flux?
The normal automatic calculation uses:
https://services.swpc.noaa.gov/text/solar_radio_flux.txt

Q6. Is current-space-weather-indices.txt used?
No. This software intentionally does not use current-space-weather-indices.txt for the G/T solar flux path because it is a broad current-indices summary and may contain missing RSTN radio-flux placeholders.

Q7. What is daily-solar-indices.txt used for?
It is used only for F10.7 estimate modes when the multi-frequency RSTN solar-radio spectrum is unavailable and the user confirms the warning.

Q8. What is F10.7?
F10.7 is solar radio flux at 10.7 cm, or 2800 MHz. It is useful as a solar activity index, but it is not a measured required spectrum by itself.

Q9. When is a result suitable for a final academic/high precision report?
Prefer results marked LIVE_NOAA_CURRENT or live current data from a usable current RSTN station. Manual data may also be suitable when the entered flux values are traceable and documented. Estimate modes should normally not be used as final academic/high precision measurement reports unless explicitly approved.

Q10. What does LIVE_NOAA_CURRENT mean?
The software used the latest NOAA solar_radio_flux.txt row and the nearest supported RSTN station with sufficient valid flux points.

Q11. What does LIVE_NOAA_OTHER_RSTN_CURRENT mean?
The nearest RSTN station did not have enough current valid flux values, so the next nearest usable RSTN station on the same latest NOAA date was used and disclosed.

Q12. What does PREVIOUS_NOAA_DATA_ESTIMATE mean?
The current NOAA row did not contain enough usable flux values, so a previous measured RSTN row was used after warning and confirmation. This is estimate-only.

Q13. What does F107_SCALED_NOAA_ESTIMATE mean?
A previous measured RSTN spectrum was scaled by the ratio of current F10.7 to reference-date F10.7. This is estimate-only because F10.7 is only one frequency point.

Q14. What does F107_ONLY_MODEL_ESTIMATE mean?
No measured multi-frequency spectrum was available, so the software generated a last-resort model spectrum:
S_model(f) = F10.7 * (f / 2800 MHz)^m
The spectral index m is user-visible and assumed, not measured by NOAA. This mode is for training or continuity checks, not final measured reporting.

Q15. What does MANUAL_DATA mean?
The calculation used user-entered frequency/flux pairs. The user is responsible for documenting calibration, date, source, and traceability.

Q16. How does the software choose an RSTN station?
It calculates the great-circle distance from the entered ground site to each supported RSTN station, ranks them, and selects the nearest station with enough valid positive flux values.

Q17. Which RSTN stations are supported?
Learmonth, San Vito, Sagamore Hill, and Palehua.

Q18. What if the station flux is not exactly at my operating frequency?
Inside the standard solar-flux grid, the software uses the nearest lower and nearest upper flux points around the operating frequency and performs power-law interpolation. If the operating frequency is outside the standard grid, automatic NOAA/RSTN extrapolation is stopped; use Manual mode with two traceable measured flux points from your own source that bracket the operating frequency.

Q19. Why is solar elevation required?
Solar elevation is used to estimate atmospheric attenuation. The elevation used for attenuation is clamped to at least 5 degrees for numerical stability.

Q20. What is the beam correction factor L?
L corrects for the Sun being an extended source relative to the antenna beamwidth. It is a direct input to the final G/T equation.

Q21. What are the direct inputs to the final G/T equation?
The final transparent equation uses k, y, S_rx, lambda, and L. In the text report these parameters are marked with a star. In the PDF report the corresponding row labels are bold.

Q22. What should I check before accepting a result?
Check:
- Data Validity Status.
- Data Warning.
- Solar flux source and date.
- Whether interpolation or extrapolation was used.
- P_sun and P_csky measurement quality.
- Antenna HPBW and operating frequency units.
- Solar elevation angle.
- Whether any estimate mode was used.

INPUT GUIDELINES

Ground Station Latitude:
Use decimal degrees. South is negative. Valid range: -90 to +90.

Ground Station Longitude:
Use decimal degrees. West is negative. Valid range: -180 to +180.

Operating Frequency:
Enter MHz, not GHz. Example: 8200 for 8.2 GHz.

Antenna HPBW:
Enter degrees. Use the measured or verified half-power beamwidth for the antenna at the operating frequency.

P_sun and P_csky:
Enter dBm values from the same receiver chain, bandwidth, detector mode, and calibration state. Do not change gain settings between the Sun and cold-sky measurements.

Solar Elevation Angle:
Enter degrees from the horizon. Avoid very low elevation measurements when possible because atmospheric correction becomes less reliable.

Manual Solar Flux:
Use two frequency/flux pairs in MHz and SFU. If the operating frequency is inside the standard solar-flux grid, the two manual flux frequencies must be the nearest standard frequencies that bracket the operating frequency. Standard grid: 245, 410, 610, 1415, 2695, 2800, 4995, 8800, and 15400 MHz. Example: for operating frequency 2200 MHz, use 1415 MHz and 2695 MHz.

If the operating frequency is outside the standard grid, for example above 15400 MHz such as >16 GHz, automatic NOAA/RSTN extrapolation is not recommended and the software switches to Manual input. In this case, enter two traceable measured solar-flux points from your own documented source. Those two frequencies must bracket the operating frequency and should be the nearest available measured points around it. Example: for 17000 MHz, use 15400 MHz and 18000 MHz only if those are the nearest documented measured flux points from your source. Record the source note and date/ID clearly.

DATA QUALITY GUIDELINES

Recommended for final reporting:
- LIVE_NOAA_CURRENT with current RSTN data.
- Manual values from a documented and traceable source.

Use with caution:
- LIVE_NOAA_OTHER_RSTN_CURRENT, because it uses another station but still uses current data.

Estimate-only:
- PREVIOUS_NOAA_DATA_ESTIMATE.
- F107_SCALED_NOAA_ESTIMATE.
- F107_ONLY_MODEL_ESTIMATE.

Not recommended for final academic/high precision measurement reports:
- Any F10.7-only model result.
- Any older NOAA row result without explicit approval.
- Any manual value without traceability.

MEASUREMENT BEST PRACTICES

- Keep receiver gain, bandwidth, detector settings, and integration time constant.
- Avoid clouds, rain, heavy atmospheric absorption, or low Sun elevation when possible.
- Take repeated Sun and cold-sky readings and use stable averaged values.
- Point accurately at the Sun for P_sun.
- Use nearby blank sky for P_csky.
- Record time, location, weather, receiver settings, and operator notes.
- Confirm that P_sun - P_csky is reasonable and positive.
- Review the full audit table, not only the final G/T value.

FORMULA SUMMARY

Flux interpolation:
m = log10(S2 / S1) / log10(F2 / F1)
S = S1 * (f_op / F1)^m

Wavelength:
lambda = 299.792458 / f_op_MHz

Y factor:
y = 10^((P_sun - P_csky) / 10)

Atmospheric correction:
A_atten_dB = Zenith_Attenuation / sin(elevation_used)
alpha_atm = 10^(A_atten_dB / 10)
S_rx = S / alpha_atm

Final G/T:
G/T_linear = [8 * pi * k * (y - 1)] / [S_rx * 10^-22 * lambda^2 * L]
G/T_dB_per_K = 10 * log10(G/T_linear)

TROUBLESHOOTING

Problem: Calculation stops with y <= 1.
Action: Check that P_sun is greater than P_csky and that both are in dBm from the same receiver setup.

Problem: NOAA cannot be loaded.
Action: Check internet access, try again later, or select Manual solar flux input.

Problem: The result is labeled estimate-only.
Action: Use Manual mode with documented flux values, or wait for valid NOAA RSTN data.

Problem: PDF table text is too long.
Action: This updated version wraps long text fields in the PDF table.

Problem: The operating frequency is outside the standard flux data range.
Action: Automatic NOAA/RSTN calculation is stopped and Manual mode is selected. Enter two traceable measured flux points from your own documented source that bracket the operating frequency, and confirm that they are the nearest available measured points around the operating frequency.

IMPORTANT NOTE
This program is a calculation and reporting aid. The quality of the final G/T result depends on measurement discipline, solar flux traceability, antenna pointing, calibration stability, and correct interpretation of the data-validity warning.
"""

    def show_faq_guidelines(self):
        """Open a readable FAQ / Guidelines window without changing the current calculation."""
        win = tk.Toplevel(self.root)
        win.title("FAQ / Guidelines")
        win.geometry("980x760")
        win.minsize(760, 520)

        header = tk.Label(
            win,
            text="FAQ / Guidelines",
            font=("Arial", 14, "bold"),
            bg="#2b78ad",
            fg="white",
            pady=8,
        )
        header.pack(fill="x")

        text_box = scrolledtext.ScrolledText(win, wrap="word", font=("Arial", 11), padx=12, pady=12)
        text_box.pack(fill="both", expand=True, padx=12, pady=(12, 6))
        text_box.insert(tk.END, self.get_faq_guidelines_text())
        text_box.configure(state="disabled")

        action_frame = tk.Frame(win)
        action_frame.pack(fill="x", padx=12, pady=(0, 12))

        def copy_to_clipboard():
            self.root.clipboard_clear()
            self.root.clipboard_append(self.get_faq_guidelines_text())
            messagebox.showinfo("Copied", "FAQ / Guidelines text copied to clipboard.")

        tk.Button(action_frame, text="Copy FAQ Text", command=copy_to_clipboard, width=18).pack(side="left")
        tk.Button(action_frame, text="Close", command=win.destroy, width=12).pack(side="right")

    def read_float(self, key, label, minimum=None, maximum=None):
        raw = self.entries[key].get().strip()
        if raw == "":
            raise ValueError(f"{label} is required.")
        try:
            value = float(raw)
        except ValueError as exc:
            raise ValueError(f"{label} must be a number. You entered: {raw!r}") from exc
        if minimum is not None and value < minimum:
            raise ValueError(f"{label} must be >= {minimum}.")
        if maximum is not None and value > maximum:
            raise ValueError(f"{label} must be <= {maximum}.")
        return value

    @staticmethod
    def haversine_km(lat1, lon1, lat2, lon2):
        radius_km = 6371.0088
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        d_phi = math.radians(lat2 - lat1)
        d_lambda = math.radians(lon2 - lon1)
        a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return radius_km * c

    def rank_rstn_stations(self, ground_lat, ground_lon):
        ranked = []
        for station in self.RSTN_STATIONS:
            distance = self.haversine_km(ground_lat, ground_lon, station["lat"], station["lon"])
            ranked.append({**station, "distance_km": distance})
        ranked.sort(key=lambda item: item["distance_km"])
        return ranked

    @staticmethod
    def _month_number(month_abbrev):
        months = {
            "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
            "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
            "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
        }
        return months[month_abbrev]

    @classmethod
    def _date_key_to_label(cls, date_key):
        year, month, day = date_key
        return f"{year} {month} {day:02d}"

    @classmethod
    def _date_key_to_datetime(cls, date_key):
        year, month, day = date_key
        return datetime(year, cls._month_number(month), day)

    @staticmethod
    def _parse_noaa_all_station_flux(text, stations):
        """
        Parse NOAA solar_radio_flux.txt for all supported RSTN stations.

        The NOAA product row layout after split() is:
            Year Month Day Freq Learmonth SanVito SagHill Penticton Penticton Palehua Penticton

        Missing values are -1 and are excluded. The returned dictionary is:
            {date_key: {station_name: [(freq_mhz, flux_sfu), ...], "__raw__": [raw rows]}}
        """
        month_names = {
            "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
        }
        grouped = {}
        for line in text.splitlines():
            parts = line.split()
            if len(parts) < 10:
                continue
            if not (parts[0].isdigit() and parts[1] in month_names and parts[2].isdigit()):
                continue
            try:
                year = int(parts[0])
                month = parts[1]
                day = int(parts[2])
                freq_mhz = float(parts[3])
            except (ValueError, IndexError):
                continue

            date_key = (year, month, day)
            date_bucket = grouped.setdefault(date_key, {"__raw__": []})
            date_bucket["__raw__"].append(line)
            for station in stations:
                col = station["column_index"]
                try:
                    flux = float(parts[col])
                except (ValueError, IndexError):
                    continue
                if flux > 0:
                    date_bucket.setdefault(station["name"], []).append((freq_mhz, flux))

        # Sort each station spectrum by frequency and remove duplicate frequency values by keeping the latest in the row order.
        for date_bucket in grouped.values():
            for station in stations:
                name = station["name"]
                if name not in date_bucket:
                    continue
                dedup = {}
                for freq_mhz, flux in date_bucket[name]:
                    dedup[freq_mhz] = flux
                date_bucket[name] = sorted(dedup.items(), key=lambda item: item[0])
        return grouped

    @classmethod
    def _parse_daily_solar_indices_f107(cls, text):
        """
        Parse NOAA daily-solar-indices.txt for F10.7 cm flux.

        The Daily Solar Data table rows begin with:
            YYYY MM DD F10.7cm ...
        The returned dictionary is {date_key: f107_sfu}. Invalid values are excluded.
        """
        f107_by_date = {}
        for line in text.splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue
            if not (parts[0].isdigit() and parts[1].isdigit() and parts[2].isdigit()):
                continue
            try:
                year = int(parts[0])
                month_num = int(parts[1])
                day = int(parts[2])
                f107 = float(parts[3])
            except ValueError:
                continue
            if not (1 <= month_num <= 12 and 1 <= day <= 31):
                continue
            if f107 <= 0 or f107 in (-1, -999):
                continue
            month_abbrev = datetime(year, month_num, day).strftime("%b")
            f107_by_date[(year, month_abbrev, day)] = f107
        return f107_by_date

    def _network_manual_message(self, url, exc):
        """Return a user-friendly message for NOAA/network failures and switch to Manual mode."""
        if hasattr(self, "solar_mode"):
            self.solar_mode.set("manual")
        detail = str(exc) if exc is not None else "Unknown network error"
        return (
            "NOAA online solar flux data could not be loaded.\n\n"
            "Possible reasons: no internet connection, DNS/network problem, firewall/proxy blocking access, "
            "or the NOAA website is temporarily unavailable.\n\n"
            "The software has switched Solar Flux Data Source to: Manual solar flux input.\n\n"
            "Please enter traceable manual solar flux values in the Manual Solar Flux Input section "
            "(frequency in MHz and flux in SFU), then run the calculation again. You may also check "
            "the internet connection and try Automatic NOAA/RSTN fetch later.\n\n"
            f"NOAA URL: {url}\n"
            f"Technical detail: {detail}"
        )

    def _raise_network_manual_error(self, url, exc):
        """Switch to Manual mode and stop the calculation with a readable network message."""
        raise ValueError(self._network_manual_message(url, exc))

    def _load_f107_daily_indices(self):
        """Load F10.7 from NOAA Daily Solar Data. Returns (f107_by_date, raw_tail)."""
        try:
            request = Request(self.DSD_URL, headers={"User-Agent": "GTStationAudit/1.0"})
            with urlopen(request, timeout=8) as response:
                text = response.read().decode("utf-8", errors="replace")
        except (URLError, HTTPError, TimeoutError, OSError) as exc:
            self._raise_network_manual_error(self.DSD_URL, exc)
        f107_by_date = self._parse_daily_solar_indices_f107(text)
        raw_tail = [line for line in text.splitlines() if line.strip()][-12:]
        return f107_by_date, raw_tail

    def _build_f107_scaled_estimate(self, target_date_key, previous_date_key, previous_spectrum, f107_by_date):
        """Scale a previous measured RSTN spectrum by current/reference F10.7 ratio."""
        current_f107 = f107_by_date.get(target_date_key)
        reference_f107 = f107_by_date.get(previous_date_key)
        if current_f107 is None or reference_f107 is None or reference_f107 <= 0:
            return None
        scale = current_f107 / reference_f107
        scaled_spectrum = [(freq, flux * scale) for freq, flux in previous_spectrum]
        return scaled_spectrum, current_f107, reference_f107, scale

    @staticmethod
    def _select_bracketing_points(spectrum, target_f):
        """Select the nearest lower and nearest upper flux points around target_f.

        For normal measured spectra, this returns the adjacent bracketing pair:
        lower_freq <= target_f <= upper_freq. If target_f is outside the
        available spectrum, it returns the nearest two edge points and the
        caller reports extrapolation. The F10.7-only model also uses this
        function, but it is not subject to the manual-input validation rule.
        """
        if len(spectrum) < 2:
            raise ValueError("At least two valid station flux points are required.")

        clean_spectrum = []
        for freq, flux in spectrum:
            try:
                clean_spectrum.append((float(freq), float(flux)))
            except (TypeError, ValueError):
                continue
        if len(clean_spectrum) < 2:
            raise ValueError("At least two numeric station flux points are required.")

        # Sort and de-duplicate by frequency. If duplicate frequencies exist,
        # keep the latest value in the input order.
        dedup = {}
        for freq, flux in clean_spectrum:
            dedup[freq] = flux
        spectrum = sorted(dedup.items(), key=lambda item: item[0])

        if target_f <= spectrum[0][0]:
            return spectrum[0], spectrum[1]
        if target_f >= spectrum[-1][0]:
            return spectrum[-2], spectrum[-1]

        for left, right in zip(spectrum, spectrum[1:]):
            if left[0] <= target_f <= right[0]:
                return left, right

        raise ValueError("Unable to select bracketing station flux points.")

    def _standard_flux_grid_bounds(self):
        """Return the lower and upper limits of the standard solar-flux grid."""
        grid = list(self.STANDARD_SOLAR_FLUX_FREQUENCIES_MHZ)
        if len(grid) < 2:
            raise ValueError("Standard solar-flux frequency grid is not configured.")
        return grid[0], grid[-1]

    def _is_outside_standard_flux_grid(self, target_f):
        """Return True when target_f is outside the normal standard flux grid."""
        low, high = self._standard_flux_grid_bounds()
        tol = self.FREQUENCY_MATCH_TOLERANCE_MHZ
        return target_f < (low - tol) or target_f > (high + tol)

    def _required_standard_flux_pair(self, target_f):
        """Return the required adjacent standard flux frequencies for target_f.

        Manual input must use this exact adjacent pair when the operating
        frequency is inside the standard solar-flux frequency grid. For
        example, 2200 MHz requires 1415 and 2695 MHz.

        If target_f is outside the grid, this function raises ValueError so
        the caller can use the special outside-grid manual validation path.
        """
        grid = list(self.STANDARD_SOLAR_FLUX_FREQUENCIES_MHZ)
        if len(grid) < 2:
            raise ValueError("Standard solar-flux frequency grid is not configured.")

        if self._is_outside_standard_flux_grid(target_f):
            raise ValueError("Operating Frequency is outside the standard solar-flux frequency grid.")

        # Exact first grid point: use the first two points. For any other exact
        # grid point, use the previous point and the exact point to avoid using
        # a point above when the operating frequency already has a measured value.
        for idx, freq in enumerate(grid):
            if abs(target_f - freq) <= self.FREQUENCY_MATCH_TOLERANCE_MHZ:
                if idx == 0:
                    return grid[0], grid[1]
                return grid[idx - 1], grid[idx]

        for lower, upper in zip(grid, grid[1:]):
            if lower < target_f < upper:
                return lower, upper

        raise ValueError("Unable to determine the required standard bracketing flux frequencies.")

    def _outside_grid_manual_guidance(self, target_f, entered):
        """Build guidance text for operation outside the standard frequency grid."""
        grid_text = ", ".join(f"{freq:.0f}" for freq in self.STANDARD_SOLAR_FLUX_FREQUENCIES_MHZ)
        low, high = self._standard_flux_grid_bounds()
        return (
            "Operating Frequency is outside the standard solar-flux frequency grid.\n\n"
            f"Operating Frequency: {target_f:.6g} MHz\n"
            f"Standard grid range: {low:.0f} to {high:.0f} MHz\n"
            f"Standard grid: {grid_text} MHz\n\n"
            "Automatic NOAA/RSTN interpolation or extrapolation is not recommended outside this grid.\n\n"
            "Use Manual solar flux input with two traceable measured flux frequencies from your own documented source. "
            "Those two manual frequencies must bracket the operating frequency, and they should be the nearest available "
            "measured frequencies around the operating frequency from your own measurement set.\n\n"
            f"Entered manual flux frequencies: {entered[0]:.6g} MHz and {entered[1]:.6g} MHz"
        )

    def _validate_manual_flux_pair(self, target_f, mf1, mf2):
        """Validate manual flux frequencies for normal and outside-grid cases.

        Inside the standard grid, the user must enter the adjacent standard
        bracketing pair. Outside the grid, the user may enter their own
        measured pair, but it must bracket the operating frequency and the user
        must explicitly confirm that the values are traceable and nearest
        available measured points.
        """
        entered = sorted([float(mf1), float(mf2)])
        tol = self.FREQUENCY_MATCH_TOLERANCE_MHZ

        if self._is_outside_standard_flux_grid(target_f):
            if not (entered[0] < target_f < entered[1]):
                guidance = self._outside_grid_manual_guidance(target_f, entered)
                raise ValueError(
                    guidance +
                    "\n\nERROR: For outside-grid operation, Manual Flux Frequency 1 and Manual Flux Frequency 2 "
                    "must put the Operating Frequency between them. Example: for 17000 MHz, use two documented "
                    "manual measured frequencies such as 15400 MHz and 18000 MHz if those are the nearest available "
                    "measured points from your source."
                )

            guidance = self._outside_grid_manual_guidance(target_f, entered)
            proceed = messagebox.askyesno(
                "Outside Standard Solar-Flux Grid",
                guidance +
                "\n\nThe software cannot verify that these are truly the nearest measured frequencies from your own source. "
                "Continue only if your manual flux values are traceable, documented, and the nearest available measured "
                "points around the operating frequency.\n\n"
                "Choose Yes to continue with Manual input. Choose No to stop and edit the manual flux frequencies."
            )
            if not proceed:
                raise ValueError("Calculation stopped. Edit Manual Flux Frequency 1 and 2 to use traceable bracketing measured values.")
            return entered[0], entered[1]

        required_f1, required_f2 = self._required_standard_flux_pair(target_f)
        required = [required_f1, required_f2]
        if abs(entered[0] - required[0]) <= tol and abs(entered[1] - required[1]) <= tol:
            return required_f1, required_f2

        grid_text = ", ".join(f"{freq:.0f}" for freq in self.STANDARD_SOLAR_FLUX_FREQUENCIES_MHZ)
        raise ValueError(
            "Manual Flux Frequency 1 and Manual Flux Frequency 2 must be the nearest standard frequencies "
            "that bracket the Operating Frequency.\n\n"
            f"Operating Frequency: {target_f:.6g} MHz\n"
            f"Required manual flux frequencies: {required_f1:.0f} MHz and {required_f2:.0f} MHz\n"
            f"Entered manual flux frequencies: {entered[0]:.6g} MHz and {entered[1]:.6g} MHz\n\n"
            "Example: if Operating Frequency is 2200 MHz, enter Flux Frequency 1 = 1415 MHz "
            "and Flux Frequency 2 = 2695 MHz.\n\n"
            f"Allowed standard frequency grid: {grid_text} MHz"
        )

    def _raise_outside_grid_auto_error(self, target_f):
        """Stop automatic calculation outside the standard grid and switch to Manual mode."""
        if hasattr(self, "solar_mode"):
            self.solar_mode.set("manual")
        grid_text = ", ".join(f"{freq:.0f}" for freq in self.STANDARD_SOLAR_FLUX_FREQUENCIES_MHZ)
        low, high = self._standard_flux_grid_bounds()
        raise ValueError(
            "Operating Frequency is outside the standard NOAA/RSTN solar-flux frequency grid.\n\n"
            f"Operating Frequency: {target_f:.6g} MHz\n"
            f"Standard grid range: {low:.0f} to {high:.0f} MHz\n"
            f"Standard grid: {grid_text} MHz\n\n"
            "Automatic NOAA/RSTN calculation has been stopped and Solar Flux Data Source has been switched to Manual solar flux input.\n\n"
            "Please enter two traceable manual solar-flux frequencies and flux values from your own documented measurement source. "
            "The two manual frequencies must bracket the operating frequency and should be the nearest available measured points "
            "around the operating frequency.\n\n"
            "Example: if Operating Frequency is 17000 MHz, enter two documented measured flux points around 17000 MHz, "
            "such as 15400 MHz and 18000 MHz only if those are the nearest available measured values from your source."
        )

    def _read_manual_float(self, key, label, minimum=None, maximum=None):
        raw = self.manual_entries[key].get().strip()
        if raw == "":
            raise ValueError(f"{label} is required for Manual solar flux mode.")
        try:
            value = float(raw)
        except ValueError as exc:
            raise ValueError(f"{label} must be a number. You entered: {raw!r}") from exc
        if minimum is not None and value < minimum:
            raise ValueError(f"{label} must be >= {minimum}.")
        if maximum is not None and value > maximum:
            raise ValueError(f"{label} must be <= {maximum}.")
        return value

    def get_manual_solar_data(self, target_f, ground_lat, ground_lon):
        """Return user-supplied solar flux pairs. No hidden fallback data are used."""
        ranked = self.rank_rstn_stations(ground_lat, ground_lon)
        mf1 = self._read_manual_float("mf1", "Manual Flux Frequency 1", minimum=1e-9)
        ms1 = self._read_manual_float("ms1", "Manual Flux 1", minimum=1e-12)
        mf2 = self._read_manual_float("mf2", "Manual Flux Frequency 2", minimum=1e-9)
        ms2 = self._read_manual_float("ms2", "Manual Flux 2", minimum=1e-12)
        if abs(mf1 - mf2) <= 1e-12:
            raise ValueError("Manual Flux Frequency 1 and Frequency 2 must be different.")
        self._validate_manual_flux_pair(target_f, mf1, mf2)
        spectrum = sorted([(mf1, ms1), (mf2, ms2)], key=lambda item: item[0])
        (f1, s1), (f2, s2) = self._select_bracketing_points(spectrum, target_f)
        data_date = self.manual_entries["mdate"].get().strip() or "Manual input"
        manual_note = self.manual_entries["mnote"].get().strip() or "User-supplied solar flux values"
        interpolation_mode = "Interpolation" if f1 <= target_f <= f2 else "Extrapolation"
        outside_standard_grid = self._is_outside_standard_flux_grid(target_f)
        noaa_status = "Manual solar flux mode selected; NOAA automatic data were not used."
        manual_data_warning = (
            "Manual data are used outside the standard solar-flux frequency grid. The user confirmed that the manual flux "
            "frequencies bracket the operating frequency and are traceable, documented, and the nearest available measured "
            "points from their own source."
            if outside_standard_grid else
            "Manual data are used. The user is responsible for traceability, calibration source, and date/time of the entered solar flux values."
        )
        manual_selection_note = (
            "Manual solar flux input selected outside the standard grid; NOAA/RSTN automatic extrapolation was not used."
            if outside_standard_grid else
            "Manual solar flux input selected; nearest RSTN station is shown only for geographic context."
        )
        return {
            "f1": f1,
            "s1": s1,
            "f2": f2,
            "s2": s2,
            "spectrum": spectrum,
            "data_date": data_date,
            "data_age_days": None,
            "spectrum_data_date": data_date,
            "spectrum_age_days": None,
            "f107_current": None,
            "f107_reference": None,
            "f107_scale": None,
            "f107_spectral_index": None,
            "f107_note": "Manual mode - F10.7 not used.",
            "raw_noaa": [manual_note],
            "noaa_status": noaa_status,
            "source_mode": "Manual user-supplied solar flux",
            "source_type": "Manual input",
            "data_validity_status": "MANUAL_DATA",
            "data_warning": manual_data_warning,
            "source_url": "Manual input - no NOAA URL used for flux values",
            "station": "Manual input",
            "station_short": "Manual",
            "station_utc_label": "User supplied",
            "station_lat": None,
            "station_lon": None,
            "station_location": manual_note,
            "station_distance_km": None,
            "nearest_station": ranked[0]["name"],
            "nearest_station_distance_km": ranked[0]["distance_km"],
            "station_selection_note": manual_selection_note,
            "interpolation_mode": interpolation_mode,
            "ranked_stations": ranked,
        }

    def _read_f107_spectral_index(self):
        """
        Read the user-visible spectral index used only for last-resort F10.7-only estimates.
        This is an assumed model parameter, not a NOAA-measured value.
        """
        raw = self.f107_index_entry.get().strip() if hasattr(self, "f107_index_entry") else "0.6"
        if raw == "":
            raise ValueError("F10.7-only spectral index m is required for F10.7-only estimate mode.")
        try:
            value = float(raw)
        except ValueError as exc:
            raise ValueError(f"F10.7-only spectral index m must be numeric. You entered: {raw!r}") from exc
        if not (-5.0 <= value <= 5.0):
            raise ValueError("F10.7-only spectral index m must be between -5 and +5.")
        return value

    def _build_f107_only_model_spectrum(self, target_f, f107_value, spectral_index):
        """
        Build an F10.7-only model spectrum on the standard RSTN frequency grid.

        This is a last-resort model:
            S_model(f) = F10.7 * (f / 2800 MHz)^m

        It is not a replacement for measured multi-frequency RSTN data.
        """
        rstn_grid_mhz = [245.0, 410.0, 610.0, 1415.0, 2695.0, 4995.0, 8800.0, 15400.0]
        spectrum = [(freq, f107_value * (freq / 2800.0) ** spectral_index) for freq in rstn_grid_mhz]
        # Keep the whole grid for traceability; bracketing points are selected later.
        return spectrum

    def _latest_f107_from_daily_indices(self):
        """Return latest valid F10.7 from daily-solar-indices.txt as (date_key, value, raw_tail)."""
        f107_by_date, raw_tail = self._load_f107_daily_indices()
        if not f107_by_date:
            return None
        latest_key = sorted(f107_by_date.keys(), key=self._date_key_to_datetime, reverse=True)[0]
        return latest_key, f107_by_date[latest_key], raw_tail

    def _confirm_f107_only_estimate(self, f107_date_label, f107_value, spectral_index, reason):
        """Show a readable F10.7-only estimate warning.

        Important:
        - Use real newline characters (\n), not the literal text "\\n".
        - Return a compact one-line version for audit/PDF table cells.
        """
        warning = (
            "WARNING: No usable multi-frequency RSTN solar-radio spectrum is available, "
            "and Manual solar flux mode was not selected.\n\n"
            "The software can produce a LAST-RESORT F10.7-ONLY MODEL ESTIMATE using NOAA "
            f"F10.7 = {f107_value:.1f} SFU at 2800 MHz from {f107_date_label} and the assumed "
            f"spectral index m = {spectral_index:.3f}.\n\n"
            "This is NOT a directly measured solar flux value at the required spectrum, "
            "NOT a current RSTN spectrum, and NOT recommended as a final academic/high precision "
            "measurement report. Use it only for training, continuity checks, or explicitly "
            "approved engineering estimates.\n\n"
            f"Reason: {reason}\n\n"
            "Choose Yes to continue with the F10.7-only estimate.\n"
            "Choose No to stop and enter Manual solar flux values."
        )
        proceed = messagebox.askyesno("Last-Resort F10.7-Only Estimate", warning)
        if not proceed:
            self.solar_mode.set("manual")
            raise ValueError("Calculation stopped by user. Manual solar flux input mode is now selected.")
        return " ".join(warning.split())

    def _f107_only_solar_data(self, target_f, ground_lat, ground_lon, reason, latest_noaa_label="N/A"):
        """Return last-resort F10.7-only modeled spectrum after user confirmation."""
        ranked = self.rank_rstn_stations(ground_lat, ground_lon)
        latest = self._latest_f107_from_daily_indices()
        if latest is None:
            raise ValueError(
                "No valid RSTN spectrum is available and NOAA daily-solar-indices.txt did not provide a valid F10.7 value. "
                "Switch to Manual solar flux input."
            )
        f107_date_key, f107_value, f107_raw_tail = latest
        f107_date_label = self._date_key_to_label(f107_date_key)
        spectral_index = self._read_f107_spectral_index()
        selected_spectrum = self._build_f107_only_model_spectrum(target_f, f107_value, spectral_index)
        data_warning = self._confirm_f107_only_estimate(f107_date_label, f107_value, spectral_index, reason)
        (f1, s1), (f2, s2) = self._select_bracketing_points(selected_spectrum, target_f)
        interpolation_mode = "Interpolation" if f1 <= target_f <= f2 else "Extrapolation"

        f107_note = (
            f"F10.7-only model estimate: S_model(f) = F10.7 * (f/2800 MHz)^m, "
            f"F10.7={f107_value:.1f} SFU, m={spectral_index:.3f}. "
            "This is an assumed spectral model and not measured RSTN flux."
        )
        raw_rows = [
            "--- NOAA daily-solar-indices.txt F10.7 context ---",
            *f107_raw_tail,
            "--- F10.7-only model warning ---",
            data_warning,
        ]
        return {
            "f1": f1,
            "s1": s1,
            "f2": f2,
            "s2": s2,
            "spectrum": selected_spectrum,
            "data_date": f107_date_label,
            "latest_noaa_date": latest_noaa_label,
            "data_age_days": None,
            "spectrum_data_date": "No measured RSTN spectrum used",
            "spectrum_age_days": None,
            "f107_current": f107_value,
            "f107_reference": None,
            "f107_scale": None,
            "f107_spectral_index": spectral_index,
            "f107_note": f107_note,
            "raw_noaa": raw_rows,
            "noaa_status": data_warning + " " + f107_note,
            "source_mode": "Automatic last-resort F10.7-only spectral model - ESTIMATE ONLY",
            "source_type": "F10.7-only estimate",
            "data_validity_status": "F107_ONLY_MODEL_ESTIMATE",
            "data_warning": data_warning,
            "source_url": self.DSD_URL,
            "station": "F10.7-only model",
            "station_short": "F10.7 model",
            "station_utc_label": "Daily index",
            "station_lat": None,
            "station_lon": None,
            "station_location": "NOAA daily-solar-indices.txt; model spectrum generated from F10.7 at 2800 MHz",
            "station_distance_km": None,
            "nearest_station": ranked[0]["name"],
            "nearest_station_distance_km": ranked[0]["distance_km"],
            "station_selection_note": (
                "No measured RSTN station spectrum was used. Last-resort F10.7-only model selected after user confirmation."
            ),
            "interpolation_mode": interpolation_mode,
            "ranked_stations": ranked,
        }

    def get_live_solar_data(self, target_f, ground_lat, ground_lon):
        """Return solar flux data from NOAA/RSTN, with F10.7-only model as the final warned last resort."""
        ranked = self.rank_rstn_stations(ground_lat, ground_lon)
        nearest = ranked[0]

        if self._is_outside_standard_flux_grid(target_f):
            self._raise_outside_grid_auto_error(target_f)

        text = None
        noaa_load_error = None
        try:
            request = Request(self.NOAA_URL, headers={"User-Agent": "GTStationAudit/1.0"})
            with urlopen(request, timeout=8) as response:
                text = response.read().decode("utf-8", errors="replace")
        except (URLError, HTTPError, TimeoutError, OSError) as exc:
            noaa_load_error = exc

        if text is None:
            # Network/DNS/website failures should not fall through to F10.7 estimate mode,
            # because F10.7 also requires online NOAA access. Stop cleanly and guide the
            # user to Manual solar flux input instead of showing raw urllib errors.
            self._raise_network_manual_error(self.NOAA_URL, noaa_load_error)

        grouped = self._parse_noaa_all_station_flux(text, self.RSTN_STATIONS)
        if not grouped:
            return self._f107_only_solar_data(
                target_f,
                ground_lat,
                ground_lon,
                reason="NOAA solar_radio_flux.txt loaded, but no valid dated positive RSTN flux rows could be parsed.",
                latest_noaa_label="N/A - no parsed RSTN date",
            )

        date_keys = sorted(grouped.keys(), key=self._date_key_to_datetime, reverse=True)
        newest_date_key = date_keys[0]
        latest_date_label = self._date_key_to_label(newest_date_key)
        selected_station = None
        selected_spectrum = None
        selected_date_key = None
        station_current_but_not_nearest = False

        # Preferred case: current/latest NOAA row, nearest usable station.
        for station in ranked:
            spectrum = grouped.get(newest_date_key, {}).get(station["name"], [])
            if len(spectrum) >= 2:
                selected_station = station
                selected_spectrum = spectrum
                selected_date_key = newest_date_key
                station_current_but_not_nearest = station["name"] != nearest["name"]
                break

        # Estimate case: no station has enough positive flux points on newest date.
        # First try a traceable F10.7-scaled estimate: scale a previous measured RSTN spectrum
        # by current/reference F10.7 from daily-solar-indices.txt. This is still estimate-only.
        used_previous_data = False
        used_f107_scaled_estimate = False
        f107_current = None
        f107_reference = None
        f107_scale = None
        f107_spectral_index = None
        f107_note = "N/A"
        f107_raw_tail = []
        previous_spectrum_date_key = None

        if selected_station is None:
            candidate_station = None
            candidate_spectrum = None
            candidate_date_key = None
            for date_key in date_keys[1:]:
                for station in ranked:
                    spectrum = grouped.get(date_key, {}).get(station["name"], [])
                    if len(spectrum) >= 2:
                        candidate_station = station
                        candidate_spectrum = spectrum
                        candidate_date_key = date_key
                        break
                if candidate_station is not None:
                    break

            if candidate_station is not None:
                try:
                    f107_by_date, f107_raw_tail = self._load_f107_daily_indices()
                    scaled = self._build_f107_scaled_estimate(newest_date_key, candidate_date_key, candidate_spectrum, f107_by_date)
                except Exception as exc:
                    if "NOAA online solar flux data could not be loaded" in str(exc):
                        raise
                    scaled = None
                    f107_raw_tail = []
                if scaled is not None:
                    selected_station = candidate_station
                    selected_spectrum, f107_current, f107_reference, f107_scale = scaled
                    selected_date_key = newest_date_key
                    previous_spectrum_date_key = candidate_date_key
                    used_f107_scaled_estimate = True
                    f107_note = (
                        f"F10.7-scaled estimate: previous measured {candidate_station['name']} spectrum from "
                        f"{self._date_key_to_label(candidate_date_key)} scaled by "
                        f"F10.7({self._date_key_to_label(newest_date_key)}) / "
                        f"F10.7({self._date_key_to_label(candidate_date_key)}) = {f107_current:.1f} / {f107_reference:.1f} = {f107_scale:.5f}."
                    )
                else:
                    selected_station = candidate_station
                    selected_spectrum = candidate_spectrum
                    selected_date_key = candidate_date_key
                    previous_spectrum_date_key = candidate_date_key
                    used_previous_data = True

        if selected_station is None:
            return self._f107_only_solar_data(
                target_f,
                ground_lat,
                ground_lon,
                reason=(
                    "NO supported RSTN station in solar_radio_flux.txt had at least two valid positive flux values "
                    "on the latest row or any previous parsed row."
                ),
                latest_noaa_label=latest_date_label,
            )

        newest_dt = self._date_key_to_datetime(newest_date_key)
        selected_dt = self._date_key_to_datetime(selected_date_key)
        spectrum_dt = self._date_key_to_datetime(previous_spectrum_date_key) if previous_spectrum_date_key else selected_dt
        data_age_days = max(0, (newest_dt - selected_dt).days)
        spectrum_age_days = max(0, (newest_dt - spectrum_dt).days)
        data_date = self._date_key_to_label(selected_date_key)
        spectrum_data_date = self._date_key_to_label(previous_spectrum_date_key) if previous_spectrum_date_key else data_date
        raw_rows = grouped.get(previous_spectrum_date_key or selected_date_key, {}).get("__raw__", [])
        if f107_raw_tail:
            raw_rows = raw_rows + ["--- Daily Solar Data F10.7 lines used for estimate context ---"] + f107_raw_tail

        if used_f107_scaled_estimate:
            data_validity_status = "F107_SCALED_NOAA_ESTIMATE"
            source_type = "NOAA F10.7 estimate"
            source_mode = "Automatic F10.7-scaled estimate from NOAA previous measured RSTN spectrum - ESTIMATE ONLY"
            age_policy = (
                f"Previous spectrum age is within the preferred <= {self.PREVIOUS_NOAA_RECOMMENDED_LIMIT_DAYS} day window."
                if spectrum_age_days <= self.PREVIOUS_NOAA_RECOMMENDED_LIMIT_DAYS
                else f"Previous spectrum age exceeds the preferred {self.PREVIOUS_NOAA_RECOMMENDED_LIMIT_DAYS} day window. "
                     "Use Manual solar flux input for a final academic/high precision measurement report unless this estimate is explicitly acceptable."
            )
            data_warning = (
                f"WARNING: Latest NOAA solar_radio_flux.txt date {latest_date_label} did not contain a usable multi-frequency RSTN spectrum. "
                f"The calculation can estimate the missing spectrum by scaling the previous measured {selected_station['name']} spectrum from "
                f"{spectrum_data_date} using NOAA F10.7 cm flux from daily-solar-indices.txt. "
                f"This is ESTIMATE ONLY because F10.7 is a 2800 MHz solar-activity index, not a measured spectrum at the operating frequency. "
                f"{age_policy}"
            )
            noaa_status = data_warning + " " + f107_note
            proceed = messagebox.askyesno(
                "F10.7-Scaled Estimate Only",
                data_warning + "\n\n" + f107_note + "\n\n"
                "Choose Yes to continue using this estimate.\n"
                "Choose No to stop and enter Manual solar flux values instead.",
            )
            if not proceed:
                self.solar_mode.set("manual")
                raise ValueError("Calculation stopped by user. Manual solar flux input mode is now selected.")
            selection_note = (
                f"F10.7-scaled estimate used because the latest NOAA RSTN spectrum was incomplete. "
                f"Measured spectrum source: {selected_station['name']} on {spectrum_data_date}. {f107_note}"
            )
        elif used_previous_data:
            data_validity_status = "PREVIOUS_NOAA_DATA_ESTIMATE"
            source_type = "NOAA previous data"
            source_mode = "Automatic NOAA previous valid RSTN row - ESTIMATE ONLY"
            age_policy = (
                f"Data age is within the preferred <= {self.PREVIOUS_NOAA_RECOMMENDED_LIMIT_DAYS} day window."
                if data_age_days <= self.PREVIOUS_NOAA_RECOMMENDED_LIMIT_DAYS
                else f"Data age exceeds the preferred {self.PREVIOUS_NOAA_RECOMMENDED_LIMIT_DAYS} day window. "
                     "Use Manual solar flux input for a final academic/high precision measurement report unless this estimate is explicitly acceptable."
            )
            data_warning = (
                f"WARNING: Current/latest NOAA date {latest_date_label} did not contain at least two valid positive flux values "
                f"for any supported RSTN station. This calculation can use previous NOAA solar_radio_flux.txt data from {data_date} "
                f"({data_age_days} day(s) older than the latest NOAA row). Treat G/T as ESTIMATE ONLY, not a current measurement report. "
                f"{age_policy}"
            )
            noaa_status = data_warning
            proceed = messagebox.askyesno(
                "Previous NOAA Data - Estimate Only",
                data_warning + "\n\nDo you want to proceed with this estimated calculation?\n\n"
                "Choose Yes to continue using previous NOAA data as ESTIMATE ONLY.\n"
                "Choose No to stop and enter Manual solar flux values instead.",
            )
            if not proceed:
                self.solar_mode.set("manual")
                raise ValueError("Calculation stopped by user. Manual solar flux input mode is now selected.")
            selection_note = (
                f"Previous NOAA data used because the latest NOAA row ({latest_date_label}) did not contain enough valid flux values. "
                f"Station selected by nearest usable data on {data_date}: {selected_station['name']}."
            )
        elif station_current_but_not_nearest:
            data_validity_status = "LIVE_NOAA_OTHER_RSTN_CURRENT"
            source_type = "Live data"
            source_mode = "Automatic NOAA current row; nearest usable RSTN station"
            data_warning = (
                f"Nearest station {nearest['name']} did not have at least two valid positive flux values on latest NOAA date "
                f"{latest_date_label}; next nearest usable station {selected_station['name']} was used."
            )
            noaa_status = "Live NOAA solar_radio_flux.txt loaded; current/latest row used from nearest usable RSTN station."
            selection_note = data_warning
        else:
            data_validity_status = "LIVE_NOAA_CURRENT"
            source_type = "Live data"
            source_mode = "Automatic NOAA current row; nearest RSTN station"
            data_warning = "None. Current/latest NOAA row used."
            noaa_status = f"Live NOAA solar_radio_flux.txt loaded; latest NOAA row used for nearest RSTN station: {selected_station['name']}."
            selection_note = "Nearest station had sufficient valid NOAA flux data on the latest NOAA row."

        (f1, s1), (f2, s2) = self._select_bracketing_points(selected_spectrum, target_f)
        interpolation_mode = "Interpolation" if f1 <= target_f <= f2 else "Extrapolation"
        return {
            "f1": f1,
            "s1": s1,
            "f2": f2,
            "s2": s2,
            "spectrum": selected_spectrum,
            "data_date": data_date,
            "latest_noaa_date": latest_date_label,
            "data_age_days": data_age_days,
            "spectrum_data_date": spectrum_data_date,
            "spectrum_age_days": spectrum_age_days,
            "f107_current": f107_current,
            "f107_reference": f107_reference,
            "f107_scale": f107_scale,
            "f107_spectral_index": f107_spectral_index,
            "f107_note": f107_note,
            "raw_noaa": raw_rows,
            "noaa_status": noaa_status,
            "source_mode": source_mode,
            "source_type": source_type,
            "data_validity_status": data_validity_status,
            "data_warning": data_warning,
            "source_url": self.NOAA_URL,
            "station": selected_station["name"],
            "station_short": selected_station["short"],
            "station_utc_label": selected_station["utc_label"],
            "station_lat": selected_station["lat"],
            "station_lon": selected_station["lon"],
            "station_location": selected_station["location"],
            "station_distance_km": selected_station["distance_km"],
            "nearest_station": nearest["name"],
            "nearest_station_distance_km": nearest["distance_km"],
            "station_selection_note": selection_note,
            "interpolation_mode": interpolation_mode,
            "ranked_stations": ranked,
        }

    def perform_math(self):
        k = 1.380649e-23
        ground_lat = self.read_float("lat", "Ground Station Latitude", minimum=-90.0, maximum=90.0)
        ground_lon = self.read_float("lon", "Ground Station Longitude", minimum=-180.0, maximum=180.0)
        f_op = self.read_float("freq", "Operating Frequency", minimum=1e-9)
        bw = self.read_float("bw", "Antenna HPBW", minimum=1e-9)
        psun = self.read_float("psun", "P_sun")
        pcsky = self.read_float("pcsky", "P_csky")
        el = self.read_float("el", "Solar Elevation Angle", minimum=0.0, maximum=90.0)

        if self.solar_mode.get() == "manual":
            solar = self.get_manual_solar_data(f_op, ground_lat, ground_lon)
        else:
            solar = self.get_live_solar_data(f_op, ground_lat, ground_lon)
        f1 = solar["f1"]
        s1 = solar["s1"]
        f2 = solar["f2"]
        s2 = solar["s2"]
        raw_noaa = solar["raw_noaa"]
        noaa_status = solar["noaa_status"]
        data_date = solar["data_date"]
        source_mode = solar["source_mode"]
        source_type = solar["source_type"]
        data_validity_status = solar["data_validity_status"]
        data_warning = solar["data_warning"]
        data_age_days = solar.get("data_age_days")
        spectrum_data_date = solar.get("spectrum_data_date", data_date)
        spectrum_age_days = solar.get("spectrum_age_days")
        f107_current = solar.get("f107_current")
        f107_reference = solar.get("f107_reference")
        f107_scale = solar.get("f107_scale")
        f107_spectral_index = solar.get("f107_spectral_index")
        f107_note = solar.get("f107_note", "N/A")
        latest_noaa_date = solar.get("latest_noaa_date", "N/A")
        interpolation_mode = solar.get("interpolation_mode", "N/A")
        source_url = solar["source_url"]
        station = solar["station"]
        station_short = solar["station_short"]
        station_utc_label = solar["station_utc_label"]
        station_lat = solar["station_lat"]
        station_lon = solar["station_lon"]
        station_location = solar["station_location"]
        station_distance_km = solar["station_distance_km"]
        nearest_station = solar["nearest_station"]
        nearest_station_distance_km = solar["nearest_station_distance_km"]
        station_selection_note = solar["station_selection_note"]
        ranked_stations = solar["ranked_stations"]
        selected_spectrum = solar["spectrum"]

        z_atten = 0.046
        sun_opt_hpbw = 0.525

        # 1. Nearest-station flux interpolation exponent and solar flux density.
        m_exp = math.log10(s2 / s1) / math.log10(f2 / f1)
        m_flux = s1 * (f_op / f1) ** m_exp

        # 2. Wavelength in meters because f_op is in MHz.
        m_wave = 299.792458 / f_op

        # 3. Effective RF solar diameter.
        f_ghz = f_op / 1000.0
        m_theta_s = sun_opt_hpbw * math.sqrt(1 + (0.14 / (f_ghz ** 2)))

        # 4. Beam correction factor.
        ln2 = math.log(2)
        ratio_sq = (m_theta_s / bw) ** 2
        if ratio_sq <= 1e-12:
            m_beam_l = 1.0
        else:
            m_beam_l = (1 - math.exp(-ln2 * ratio_sq)) / (ln2 * ratio_sq)

        # 5. Y factor.
        p_delta = psun - pcsky
        m_y_lin = 10 ** (p_delta / 10)
        if m_y_lin <= 1.0:
            raise ValueError("P_sun must be greater than P_csky so that y > 1 and G/T is physically valid.")

        # 6. Atmospheric attenuation. Clamp elevation at 5 degrees for path-loss stability.
        # NOAA solar flux is treated as the above-atmosphere reference flux.
        # alpha_atm is a linear atmospheric loss factor (>1). The solar flux at
        # the antenna reference plane is therefore S_rx = S / alpha_atm.
        el_for_atten = max(el, 5.0)
        a_atten = z_atten / math.sin(math.radians(el_for_atten))
        m_alpha_lin = 10 ** (a_atten / 10)
        m_flux_rx = m_flux / m_alpha_lin

        # 7. Final G/T.
        # Reference-plane transparent form:
        #   numerator   = 8*pi*k*(y - 1)
        #   denominator = S_rx*1e-22*lambda^2*L
        # This is equivalent to multiplying the unattenuated-flux result by alpha_atm.
        denominator = m_flux_rx * 1e-22 * (m_wave ** 2) * m_beam_l
        numerator = 8 * math.pi * k * (m_y_lin - 1)
        m_gt_lin = numerator / denominator
        if m_gt_lin <= 0:
            raise ValueError("Calculated G/T is non-positive. Check input power values and beamwidth.")
        m_gt_dbk = 10 * math.log10(m_gt_lin)

        return locals()

    def _solar_flux_input_rule_text(self, m):
        """Return the report text that explains the solar-flux input rule used."""
        grid_text = ", ".join(f"{freq:.0f}" for freq in self.STANDARD_SOLAR_FLUX_FREQUENCIES_MHZ)
        f_op = m.get("f_op")
        f1 = m.get("f1")
        f2 = m.get("f2")
        source_type = m.get("source_type", "")
        data_status = m.get("data_validity_status", "")

        if data_status == "F107_ONLY_MODEL_ESTIMATE":
            return (
                "F10.7-only estimate mode does not use user-entered manual flux pairs. It creates an estimate-only "
                "model spectrum from F10.7 at 2800 MHz and the user-visible spectral index m; this is not recommended "
                "for final academic/high precision measurement reports."
            )

        if f_op is None or f1 is None or f2 is None:
            return "Solar-flux input rule could not be evaluated because frequency values are not available."

        if source_type == "Manual input":
            if self._is_outside_standard_flux_grid(f_op):
                return (
                    f"Manual outside-grid rule: Operating Frequency {f_op:.1f} MHz is outside the standard grid "
                    f"({grid_text} MHz). NOAA/RSTN automatic extrapolation is not used. The report uses manual "
                    f"Flux Frequency 1 = {f1:.1f} MHz and Flux Frequency 2 = {f2:.1f} MHz. These two values must "
                    "bracket the operating frequency and should be the nearest available traceable measured solar-flux "
                    "points from the user's own documented source. The software can verify bracketing but cannot verify "
                    "the user's external measurement traceability or whether closer external points exist."
                )
            required_f1, required_f2 = self._required_standard_flux_pair(f_op)
            return (
                f"Manual standard-grid rule: Operating Frequency {f_op:.1f} MHz is inside the standard solar-flux grid "
                f"({grid_text} MHz). Manual Flux Frequency 1 and 2 must be the nearest standard frequencies that "
                f"bracket the operating frequency. Required pair = {required_f1:.1f} MHz and {required_f2:.1f} MHz; "
                f"report pair used = {f1:.1f} MHz and {f2:.1f} MHz. Manual flux values must be traceable and documented."
            )

        return (
            f"Automatic NOAA/RSTN rule: the software selects the nearest available measured flux frequencies that bracket "
            f"Operating Frequency {f_op:.1f} MHz from the selected RSTN spectrum. Report pair used = {f1:.1f} MHz and "
            f"{f2:.1f} MHz. Automatic NOAA/RSTN extrapolation outside the standard grid is stopped; outside-grid work "
            "requires Manual input with traceable measured bracketing points."
        )

    def get_rows(self, m):
        """Full audit table rows: Measurement, Unit, Type, Result."""
        station_lat = "N/A" if m["station_lat"] is None else f"{m['station_lat']:.5f}"
        station_lon = "N/A" if m["station_lon"] is None else f"{m['station_lon']:.5f}"
        station_distance = "N/A" if m["station_distance_km"] is None else f"{m['station_distance_km']:.1f}"
        data_age = "N/A" if m["data_age_days"] is None else f"{m['data_age_days']}"
        return [
            ["Solar Flux Source", "Source", m["source_type"], m["source_url"]],
            ["Data Validity Status", "Status", m["source_type"], m["data_validity_status"]],
            ["Data Warning", "Text", m["source_type"], m["data_warning"]],
            ["Solar Flux Input Rule", "Rule", m["source_type"], self._solar_flux_input_rule_text(m)],
            ["Previous NOAA Policy", "Policy", "Constant", f"Allowed only after user confirmation; <= {self.PREVIOUS_NOAA_RECOMMENDED_LIMIT_DAYS} days old is preferred. Older data are estimate-only and not recommended for final academic/high precision measurement reports."],
            ["Current Indices File Used", "Yes/No", "Constant", "No - current-space-weather-indices.txt is not used for G/T solar flux calculation."],
            ["NOAA Data Date Used", "Local date", m["source_type"], m["data_date"]],
            ["Latest NOAA Date in Feed", "Local date", "Live data" if m["latest_noaa_date"] != "N/A" else m["source_type"], m["latest_noaa_date"]],
            ["NOAA Data Age", "days", "Calculate", data_age],
            ["Measured Spectrum Date", "Local date", m["source_type"], m.get("spectrum_data_date", m["data_date"])],
            ["Measured Spectrum Age", "days", "Calculate", "N/A" if m.get("spectrum_age_days") is None else f"{m['spectrum_age_days']}"],
            ["F10.7 Current", "SFU at 2800 MHz", m["source_type"], "N/A" if m.get("f107_current") is None else f"{m['f107_current']:.1f}"],
            ["F10.7 Reference", "SFU at 2800 MHz", m["source_type"], "N/A" if m.get("f107_reference") is None else f"{m['f107_reference']:.1f}"],
            ["F10.7 Scale Factor", "No Units", "Calculate", "N/A" if m.get("f107_scale") is None else f"{m['f107_scale']:.6f}"],
            ["F10.7-Only Spectral Index m", "No Units", m["source_type"], "N/A" if m.get("f107_spectral_index") is None else f"{m['f107_spectral_index']:.3f}"],
            ["F10.7 Estimate Note", "Text", m["source_type"], m.get("f107_note", "N/A")],
            ["Solar Flux Data Mode", "Mode", m["source_type"], m["source_mode"]],
            ["Station Selection Note", "Text", "Calculate", m["station_selection_note"]],
            ["Ground Station Latitude", "degrees", "Manual input", f"{m['ground_lat']:.6f}"],
            ["Ground Station Longitude", "degrees", "Manual input", f"{m['ground_lon']:.6f}"],
            ["Nearest RSTN Station", "Station", "Calculate", m["nearest_station"]],
            ["Nearest RSTN Distance", "km", "Calculate", f"{m['nearest_station_distance_km']:.1f}"],
            ["RSTN / Flux Source Used", "Station", m["source_type"], m["station"]],
            ["Station / Source Location", "Text", "Constant" if m["station_lat"] is not None else "Manual input", m["station_location"]],
            ["Station Latitude", "degrees", "Constant" if m["station_lat"] is not None else "Manual input", station_lat],
            ["Station Longitude", "degrees", "Constant" if m["station_lon"] is not None else "Manual input", station_lon],
            ["Station Distance from Ground Site", "km", "Calculate", station_distance],
            ["NOAA Station Column Time", "UTC", "Constant" if m["station_lat"] is not None else "Manual input", m["station_utc_label"]],
            ["Operating Frequency", "MHz", "Manual input", f"{m['f_op']:.1f}"],
            ["Antenna HPBW", "degrees", "Manual input", f"{m['bw']:.4f}"],
            ["P_sun", "dBm", "Manual input", f"{m['psun']:.3f}"],
            ["P_csky", "dBm", "Manual input", f"{m['pcsky']:.3f}"],
            ["Solar Elevation Angle", "degrees", "Manual input", f"{m['el']:.2f}"],
            ["Boltzmann Constant k", "J/K", "Constant", f"{m['k']:.6e}"],
            ["Zenith Attenuation", "dB", "Constant", f"{m['z_atten']:.4f}"],
            ["Sun Optical HPBW", "degrees", "Constant", f"{m['sun_opt_hpbw']:.3f}"],
            ["ln(2)", "No Units", "Constant", f"{m['ln2']:.9f}"],
            ["Elevation Used for Attenuation", "degrees", "Calculate", f"{m['el_for_atten']:.2f}"],
            ["Flux Freq. 1", "MHz", m["source_type"], f"{m['f1']:.1f}"],
            ["Station/User Flux 1", "SFU", m["source_type"], f"{m['s1']:.1f}"],
            ["Flux Freq. 2", "MHz", m["source_type"], f"{m['f2']:.1f}"],
            ["Station/User Flux 2", "SFU", m["source_type"], f"{m['s2']:.1f}"],
            ["Flux Use Mode", "Mode", "Calculate", m["interpolation_mode"]],
            ["Flux Interpolation Exponent", "No Units", "Calculate", f"{m['m_exp']:.5f}"],
            ["Interpolated Solar Flux", "SFU", "Calculate", f"{m['m_flux']:.4f}"],
            ["Operating Frequency", "GHz", "Calculate", f"{m['f_ghz']:.6f}"],
            ["Wavelength", "meters", "Calculate", f"{m['m_wave']:.5f}"],
            ["Sun Effective RF Diameter", "degrees", "Calculate", f"{m['m_theta_s']:.4f}"],
            ["Solar/Beam Ratio Squared", "No Units", "Calculate", f"{m['ratio_sq']:.6f}"],
            ["Beam Correction Factor", "No Units", "Calculate", f"{m['m_beam_l']:.5f}"],
            ["P_delta", "dB", "Calculate", f"{m['p_delta']:.3f}"],
            ["y", "No Units", "Calculate", f"{m['m_y_lin']:.5f}"],
            ["Atmospheric Attenuation", "dB", "Calculate", f"{m['a_atten']:.4f}"],
            ["Atmospheric Alpha Loss", "linear", "Calculate", f"{m['m_alpha_lin']:.5f}"],
            ["Solar Flux at Antenna Ref. Plane", "SFU", "Calculate", f"{m['m_flux_rx']:.4f}"],
            ["G/T Numerator", "SI", "Calculate", f"{m['numerator']:.6e}"],
            ["G/T Denominator", "SI", "Calculate", f"{m['denominator']:.6e}"],
            ["G/T Linear", "1/K", "Calculate", f"{m['m_gt_lin']:.6e}"],
            ["G/T", "dB/K", "Calculate", f"{m['m_gt_dbk']:.2f}"],
        ]

    def get_key_result_rows(self, m):
        """Large first-page summary table for PDF readability."""
        data_age = "N/A" if m["data_age_days"] is None else f"{m['data_age_days']} day(s)"
        return [
            ["Item", "Type", "Value"],
            ["G/T", "Calculate", f"{m['m_gt_dbk']:.2f} dB/K"],
            ["G/T Linear", "Calculate", f"{m['m_gt_lin']:.6e} 1/K"],
            ["Data Validity", m["source_type"], m["data_validity_status"]],
            ["Data Warning", m["source_type"], m["data_warning"]],
            ["Solar Flux Input Rule", m["source_type"], self._solar_flux_input_rule_text(m)],
            ["Automatic NOAA File", "Constant", "solar_radio_flux.txt only; current-space-weather-indices.txt is not used"],
            ["Solar Flux Source", m["source_type"], m["source_mode"]],
            ["Flux Date Used", m["source_type"], m["data_date"]],
            ["NOAA Data Age", "Calculate", data_age],
            ["Measured Spectrum Date", m["source_type"], m.get("spectrum_data_date", m["data_date"])],
            ["F10.7 Scaling", m["source_type"], "Not used" if m.get("f107_scale") is None else f"scale={m['f107_scale']:.6f}; current={m['f107_current']:.1f} SFU; reference={m['f107_reference']:.1f} SFU"],
            ["F10.7-Only Model", m["source_type"], "Not used" if m.get("f107_spectral_index") is None else f"F10.7={m['f107_current']:.1f} SFU, m={m['f107_spectral_index']:.3f}"],
            ["Flux Source / Station Used", m["source_type"], m["station"]],
            ["Ground Station", "Manual input", f"Lat {m['ground_lat']:.6f}, Lon {m['ground_lon']:.6f}"],
            ["Operating Frequency", "Manual input", f"{m['f_op']:.1f} MHz"],
            ["Antenna HPBW", "Manual input", f"{m['bw']:.4f} deg"],
            ["Measured Powers", "Manual input", f"P_sun {m['psun']:.3f} dBm, P_csky {m['pcsky']:.3f} dBm"],
            ["Y Factor", "Calculate", f"{m['m_y_lin']:.5f}"],
            ["Interpolated Solar Flux", "Calculate", f"{m['m_flux']:.4f} SFU ({m['interpolation_mode']})"],
            ["Solar Flux at Antenna Ref. Plane", "Calculate", f"{m['m_flux_rx']:.4f} SFU"],
            ["Beam Correction Factor", "Calculate", f"{m['m_beam_l']:.5f}"],
            ["Atmospheric Alpha Loss", "Calculate", f"{m['m_alpha_lin']:.5f}"],
        ]

    def get_spectrum_rows(self, m):
        rows = [["Frequency MHz", f"{m['station_short']} Flux SFU", "Result Type", "Use"]]
        for freq, flux in m["selected_spectrum"]:
            use_text = "Interpolation point" if freq in (m["f1"], m["f2"]) else "Reference point"
            rows.append([f"{freq:.1f}", f"{flux:.1f}", m["source_type"], use_text])
        return rows

    def get_station_ranking_rows(self, m):
        rows = [["Rank", "RSTN Station", "Location", "Distance km"]]
        for idx, station in enumerate(m["ranked_stations"], start=1):
            rows.append([str(idx), station["name"], station["location"], f"{station['distance_km']:.1f}"])
        return rows

    def get_formula_details(self):
        return [
            "MATHEMATICAL FORMULATION DETAILS:",
            "This section lists every formula that creates a calculated value shown in the audit table.",
            "Type rows identify the origin: Manual input, Live data, NOAA previous data, Constant, or Calculate.",
            "",
            "1. RSTN NEAREST-STATION SELECTION:",
            "   Input: ground station latitude phi_g and longitude lambda_g.",
            "   Each RSTN station has fixed latitude phi_s and longitude lambda_s.",
            "   Great-circle distance uses the haversine formula:",
            "   a = sin^2((phi_s - phi_g)/2) + cos(phi_g) * cos(phi_s) * sin^2((lambda_s - lambda_g)/2)",
            "   c = 2 * atan2(sqrt(a), sqrt(1 - a))",
            "   distance_km = 6371.0088 * c",
            "   The station with the smallest distance is selected first.",
            "   If that station has fewer than two valid positive flux values on the latest NOAA date,",
            "   the next nearest RSTN station with at least two valid points on that same date is used and reported.",
            "",
            "2. NOAA RSTN DATA SELECTION:",
            "   Use only the selected station column from NOAA solar_radio_flux.txt.",
            "   current-space-weather-indices.txt is not used for this calculation path.",
            "   RSTN columns used: Learmonth, San Vito, Sag Hill, or Palehua.",
            "   Ignore missing NOAA values marked -1.",
            "   Preferred automatic mode uses the latest dated NOAA row with a nearest usable RSTN station.",
            "   If the latest NOAA row has no usable supported RSTN station, the software may use F10.7-scaled estimate mode only after user confirmation.",
            "   F10.7 is the 10.7 cm solar radio flux at 2800 MHz from NOAA daily-solar-indices.txt.",
            "   F10.7 by itself is only one frequency point; for f_op other than 2800 MHz it cannot define a full spectrum.",
            "   Therefore F10.7 estimate mode scales a previous measured RSTN spectrum:",
            "   scale_F107 = F10.7_current / F10.7_reference_date",
            "   S_scaled(F_i) = S_previous(F_i) * scale_F107",
            "   The scaled spectrum is then used only as ESTIMATE data, not as a direct measured spectrum.",
            "   If F10.7 scaling is unavailable, older NOAA rows may be used only as ESTIMATE data after user confirmation.",
            "   LAST RESORT: if no measured RSTN spectrum is available and Manual mode is not selected,",
            "   the software may use F10.7-only model estimate after user confirmation:",
            "   S_model(f) = F10.7 * (f / 2800 MHz)^m",
            "   The spectral index m is a user-visible assumed parameter, not a NOAA measurement.",
            "   F10.7-only mode is training/estimate only and is not a final measured G/T report.",
            "   If NOAA daily-solar-indices.txt cannot provide F10.7, no calculation is made and Manual input is required.",
            "   Manual mode uses user-entered F1,S1 and F2,S2 values and labels the report as MANUAL_DATA.",
            "   Select F1,S1 and F2,S2 as the two nearest measured frequencies bracketing f_op.",
            "   If f_op is outside the standard solar-flux grid, automatic NOAA/RSTN extrapolation is stopped and Manual input is required.",
            "   For outside-grid Manual input, the user must provide two traceable measured flux points that bracket f_op and should be the nearest available measured points from their own source.",
            "",
            "3. FLUX INTERPOLATION EXPONENT:",
            "   m = log10(S2 / S1) / log10(F2 / F1)",
            "",
            "4. INTERPOLATED STATION SOLAR FLUX:",
            "   S = S1 * (f_op / F1)^m",
            "",
            "5. OPERATING FREQUENCY IN GHz:",
            "   f_GHz = f_op_MHz / 1000",
            "",
            "6. WAVELENGTH:",
            "   lambda = 299.792458 / f_op_MHz",
            "",
            "7. ELEVATION USED FOR ATTENUATION:",
            "   el_used = max(el, 5 degrees)",
            "",
            "8. SUN EFFECTIVE RF DIAMETER:",
            "   theta_s = Sun_Optical_HPBW * sqrt(1 + 0.14 / f_GHz^2)",
            "",
            "9. SOLAR/BEAM RATIO SQUARED:",
            "   ratio_sq = (theta_s / HPBW)^2",
            "",
            "10. BEAM CORRECTION FACTOR:",
            "   L = [1 - exp(-ln(2) * ratio_sq)] / [ln(2) * ratio_sq]",
            "   If ratio_sq is extremely close to zero, L is set to 1.0 for numerical stability.",
            "",
            "11. SUN-TO-COLD-SKY POWER DIFFERENCE:",
            "   P_delta = P_sun - P_csky",
            "",
            "12. Y FACTOR:",
            "   y = 10^(P_delta / 10)",
            "",
            "13. ATMOSPHERIC ATTENUATION:",
            "   A_atten_dB = Zenith_Attenuation / sin(el_used)",
            "",
            "14. ATMOSPHERIC ALPHA LOSS:",
            "   alpha_atm = 10^(A_atten_dB / 10)",
            "   alpha_atm is a linear loss factor greater than 1 when attenuation is positive.",
            "",
            "15. SOLAR FLUX AT ANTENNA REFERENCE PLANE:",
            "   NOAA/RSTN flux S is treated as above-atmosphere solar flux.",
            "   S_rx = S / alpha_atm",
            "",
            "16. G/T NUMERATOR:",
            "   numerator = 8 * pi * k * (y - 1)",
            "",
            "17. G/T DENOMINATOR:",
            "   denominator = S_rx * 10^-22 * lambda^2 * L",
            "",
            "18. G/T LINEAR:",
            "   G_T_linear = numerator / denominator",
            "   Equivalent expanded form: G_T_linear = [8*pi*k*(y-1)*alpha_atm] / [S*10^-22*lambda^2*L]",
            "",
            "19. G/T IN dB/K:",
            "   G_T_dB_per_K = 10 * log10(G_T_linear)",
        ]

    def get_explanation(self):
        return [
            "ENGINEERING METHODOLOGY & TRACEABILITY:",
            "The G/T ratio is calculated using measured Sun/cold-sky power difference and",
            "solar flux values from either NOAA solar_radio_flux.txt automatic mode or documented manual input.",
            "",
            "1. WORLDWIDE STATION SELECTION:",
            "   Ground Station latitude/longitude is used to compute distance to each supported RSTN site.",
            "   In automatic mode, the nearest station is selected first. If its latest NOAA row is insufficient,",
            "   the next nearest station with enough valid data on the same latest date is selected and disclosed in the table.",
            "",
            "2. NOAA DATA INTEGRATION:",
            "   The program uses only one selected RSTN station column, not an average of stations.",
            "   Missing NOAA values marked -1 are ignored.",
            "   The latest NOAA date is preferred. Older NOAA rows are allowed only as an explicit ESTIMATE after user confirmation.",
            "   There is no hidden fallback spectrum in this version.",
            "   If no measured RSTN spectrum is available and Manual mode is not selected, the last-resort path uses",
            "   NOAA daily F10.7 at 2800 MHz plus the user-visible assumed spectral index m to build a model spectrum.",
            "   This F10.7-only path is estimate-only and should not be treated as a final measured G/T report.",
            "   current-space-weather-indices.txt is intentionally excluded to avoid mixing a broad current-indices summary with the dedicated RSTN flux product.",
            "   Manual mode should use traceable lab, observatory, or documented solar flux values entered by the user.",
            "   The spectral exponent is derived from the two selected-station or manual frequencies bracketing",
            "   the operating frequency. Automatic NOAA/RSTN extrapolation outside the standard grid is not used;",
            "   outside-grid operation requires Manual input with traceable bracketing measured values.",
            "",
            "3. REFERENCE PLANE AND ATMOSPHERIC MODELING:",
            "   NOAA/RSTN flux is treated as above-atmosphere solar flux. Atmospheric loss is converted",
            "   to a linear alpha_atm factor, and the antenna-reference-plane flux is S_rx = S / alpha_atm.",
            "   Elevation is clamped to 5 degrees for numerical stability at very low angles.",
            "   Zenith attenuation is a fixed model assumption unless the user edits the constant in the script.",
            "",
            "4. BEAM CORRECTION (L):",
            "   Corrects for source extension relative to antenna beamwidth. For high-gain antennas",
            "   with small HPBW, the sun cannot be treated as a point source.",
            "   This assumes a Gaussian antenna main beam and a circular effective solar disc model.",
            "",
            "5. FIXED MODEL ASSUMPTIONS:",
            "   Boltzmann constant is exact in SI. Sun optical HPBW, RF solar diameter model coefficient,",
            "   and zenith attenuation are fixed model assumptions shown in the audit table for traceability.",
            "",
            "6. DATA VALIDITY RULES:",
            "   LIVE_NOAA_CURRENT is suitable for normal automatic reporting.",
            "   LIVE_NOAA_OTHER_RSTN_CURRENT is valid but discloses that the nearest station lacked enough current values.",
            "   PREVIOUS_NOAA_DATA_ESTIMATE is not a current report; the PDF warns that G/T is an estimate.",
            "   F107_SCALED_NOAA_ESTIMATE is estimate-only because it scales an older measured spectrum by F10.7.",
            "   F107_ONLY_MODEL_ESTIMATE is last-resort estimate-only because it creates a spectrum from F10.7 and assumed m.",
            "   MANUAL_DATA is valid only to the extent that the user's entered flux values are traceable and documented.",
            "",
            "7. INPUT VALIDATION RULES:",
            "   Latitude must be -90 to +90, longitude must be -180 to +180, frequency and HPBW must be positive,",
            "   elevation must be 0 to 90 degrees, manual flux values must be positive, and P_sun must be greater than P_csky so y > 1.",
        ]

    def is_direct_gt_parameter(self, measurement_name):
        """Return True when the row is a direct input to the final G/T equation."""
        return measurement_name in self.DIRECT_GT_PARAMETERS

    def get_direct_gt_input_rows(self, m):
        """Small teaching table showing only the direct final-equation inputs."""
        return [
            ["Parameter", "Symbol", "Value", "Role in final G/T equation"],
            ["Boltzmann Constant k", "k", f"{m['k']:.6e} J/K", "Thermal-noise conversion constant"],
            ["Y Factor", "y", f"{m['m_y_lin']:.5f}", "Sun/cold-sky power ratio from measured powers"],
            ["Solar Flux at Antenna Ref. Plane", "S_rx", f"{m['m_flux_rx']:.4f} SFU", "Atmosphere-corrected solar flux used in denominator"],
            ["Wavelength", "lambda", f"{m['m_wave']:.5f} m", "RF wavelength squared in denominator"],
            ["Beam Correction Factor", "L", f"{m['m_beam_l']:.5f}", "Finite solar-disc correction in denominator"],
        ]

    def get_traceability_sections(self, m):
        """Split the long audit table into professional PDF sections to avoid awkward page/table splits."""
        rows = self.get_rows(m)
        sections = [
            ("Data Source, Validity, and Warning", [
                "Solar Flux Source", "Data Validity Status", "Data Warning", "Solar Flux Input Rule", "Previous NOAA Policy",
                "Current Indices File Used", "NOAA Data Date Used", "Latest NOAA Date in Feed",
                "NOAA Data Age", "Measured Spectrum Date", "Measured Spectrum Age", "F10.7 Current",
                "F10.7 Reference", "F10.7 Scale Factor", "F10.7-Only Spectral Index m",
                "F10.7 Estimate Note", "Solar Flux Data Mode", "Station Selection Note",
            ]),
            ("Ground Site and RSTN Station Selection", [
                "Ground Station Latitude", "Ground Station Longitude", "Nearest RSTN Station",
                "Nearest RSTN Distance", "RSTN / Flux Source Used", "Station / Source Location",
                "Station Latitude", "Station Longitude", "Station Distance from Ground Site",
                "NOAA Station Column Time",
            ]),
            ("Measured User Inputs and Fixed Model Constants", [
                "Operating Frequency", "Antenna HPBW", "P_sun", "P_csky", "Solar Elevation Angle",
                "Boltzmann Constant k", "Zenith Attenuation", "Sun Optical HPBW", "ln(2)",
            ]),
            ("Solar Flux Interpolation and Propagation Corrections", [
                "Elevation Used for Attenuation", "Flux Freq. 1", "Station/User Flux 1",
                "Flux Freq. 2", "Station/User Flux 2", "Flux Use Mode", "Flux Interpolation Exponent",
                "Interpolated Solar Flux", "Operating Frequency", "Wavelength", "Sun Effective RF Diameter",
                "Solar/Beam Ratio Squared", "Beam Correction Factor", "Atmospheric Attenuation",
                "Atmospheric Alpha Loss", "Solar Flux at Antenna Ref. Plane",
            ]),
            ("Final G/T Equation Values", [
                "P_delta", "y", "G/T Numerator", "G/T Denominator", "G/T Linear", "G/T",
            ]),
        ]
        used_ids = set()
        output = []
        for title, names in sections:
            section_rows = []
            for idx, row in enumerate(rows):
                if idx in used_ids:
                    continue
                if row[0] in names:
                    section_rows.append(row)
                    used_ids.add(idx)
            if section_rows:
                output.append((title, [["Measurement", "Unit", "Type", "Result"]] + section_rows))
        remaining = [row for idx, row in enumerate(rows) if idx not in used_ids]
        if remaining:
            output.append(("Other Traceability Values", [["Measurement", "Unit", "Type", "Result"]] + remaining))
        return output

    def get_license_report_lines(self):
        """Return the full MIT License text for inclusion in PDF reports."""
        return [line if line else "" for line in self.MIT_LICENSE_TEXT.splitlines()]

    def _add_pdf_line_section(self, story, title, lines, h_style, body_style, subheading_style, formula_style):
        """Render explanation/formula lines with cleaner PDF typography."""
        story.append(Paragraph(title, h_style))
        for line in lines:
            text = str(line).strip()
            if not text:
                story.append(Spacer(1, 2))
                continue
            is_numbered_heading = len(text) > 2 and text[0].isdigit() and "." in text[:4]
            is_section_heading = text.endswith(":") and (text.isupper() or is_numbered_heading)
            if is_section_heading or is_numbered_heading:
                story.append(Paragraph(text, subheading_style))
            elif any(token in text for token in ["=", "log10", "sqrt", "sin", "10^", "S_model", "G_T"]):
                story.append(Paragraph(text, formula_style))
            else:
                story.append(Paragraph(text, body_style))

    def build_text_report(self, m):
        report = f"G/T Measurement Audit | {datetime.now():%Y-%m-%d %H:%M:%S}\n"
        report += f"NOAA Status: {m['noaa_status']}\n"
        report += f"NOAA Source: {m['source_url']}\n"
        report += f"RSTN Station Used: {m['station']} ({m['station_short']})\n"
        report += "* Direct input to final G/T equation: k, y, S_rx, lambda, and L.\n"
        report += "=" * 115 + "\n"
        report += f"{'Measurement':<38} | {'Unit':<12} | {'Type':<10} | Result\n"
        report += "-" * 115 + "\n"
        for row in self.get_rows(m):
            gt_prefix = "** " if row[0] == "G/T" else "   "
            direct_star = "*" if self.is_direct_gt_parameter(row[0]) else " "
            display_name = f"{direct_star}{row[0]}"
            report += f"{gt_prefix}{display_name:<35} | {row[1]:<12} | {row[2]:<10} | {row[3]}\n"
        report += "=" * 115 + f"\n{m['station'].upper()} FLUX VALUES USED:\n" + "=" * 115 + "\n"
        report += f"{'Frequency MHz':<18} | {m['station_short'] + ' Flux SFU':<20} | Type\n"
        report += "-" * 115 + "\n"
        for freq, flux in m["selected_spectrum"]:
            marker = " <== interpolation point" if freq in (m["f1"], m["f2"]) else ""
            report += f"{freq:<18.1f} | {flux:<20.1f} | {m['source_type']}{marker}\n"
        report += "=" * 115 + "\nRSTN STATION DISTANCE RANKING:\n" + "=" * 115 + "\n"
        for row in self.get_station_ranking_rows(m):
            report += f"{row[0]:<6} | {row[1]:<15} | {row[2]:<40} | {row[3]}\n"
        report += "=" * 115 + "\nRAW NOAA ROWS FOR SELECTED DATE:\n" + "=" * 115 + "\n"
        for line in m["raw_noaa"]:
            report += line + "\n"
        report += "=" * 115 + "\n"
        for line in self.get_explanation():
            report += line + "\n"
        report += "=" * 115 + "\n"
        for line in self.get_formula_details():
            report += line + "\n"
        return report

    def calculate(self):
        try:
            m = self.perform_math()
            report = self.build_text_report(m)
            self.output.delete("1.0", tk.END)
            self.output.insert(tk.END, report)
        except Exception as exc:
            messagebox.showerror("Input or Calculation Error", str(exc))

    def _pdf_paragraph(self, text, style):
        safe = str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return Paragraph(safe, style)

    def _fit_col_widths_to_a4(self, col_widths, horizontal_padding=0.64 * inch):
        """Scale table widths so A4 portrait tables never run off the page."""
        max_width = A4[0] - horizontal_padding
        total_width = sum(col_widths)
        if total_width <= max_width:
            return col_widths
        scale = max_width / total_width
        return [width * scale for width in col_widths]

    def _compact_table(self, data, col_widths, styles, paragraph_cols=None, font_size=6.0, bold_first_col_values=None):
        """
        Build a compact A4-safe ReportLab table.

        Repair notes:
        - All cells are rendered as Paragraph objects so long values wrap instead of spilling past the page edge.
        - Column widths are automatically scaled to the printable A4 width.
        - splitLongWords helps with URLs, status tokens, and NOAA file names that contain underscores.
        """
        paragraph_cols = set(paragraph_cols or [])
        bold_first_col_values = set(bold_first_col_values or [])
        col_widths = self._fit_col_widths_to_a4(col_widths)
        sheet = getSampleStyleSheet()
        cell_style = ParagraphStyle(
            "CompactCell",
            parent=sheet["BodyText"],
            fontName="Helvetica",
            fontSize=font_size,
            leading=font_size + 1.15,
            alignment=TA_LEFT,
            spaceAfter=0,
            spaceBefore=0,
            splitLongWords=1,
            wordWrap="CJK",
        )
        bold_cell_style = ParagraphStyle(
            "CompactCellBold",
            parent=cell_style,
            fontName="Helvetica-Bold",
        )
        header_style = ParagraphStyle(
            "CompactHeader",
            parent=cell_style,
            fontName="Helvetica-Bold",
            textColor=colors.whitesmoke,
        )

        converted = []
        for r_index, row in enumerate(data):
            converted_row = []
            row_label = str(row[0]) if row else ""
            for c_index, value in enumerate(row):
                # Convert every cell to a Paragraph.  This is safer than mixing raw strings
                # because raw strings do not wrap reliably when a value is long.
                if r_index == 0:
                    converted_row.append(self._pdf_paragraph(value, header_style))
                elif c_index == 0 and row_label in bold_first_col_values:
                    converted_row.append(self._pdf_paragraph(value, bold_cell_style))
                else:
                    converted_row.append(self._pdf_paragraph(value, cell_style))
            converted.append(converted_row)

        table = Table(converted, colWidths=col_widths, repeatRows=1, hAlign="LEFT", splitByRow=1)
        table.setStyle(TableStyle(styles + [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b78ad")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#888888")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7fbff")]),
            ("FONTSIZE", (0, 0), (-1, -1), font_size),
            ("LEADING", (0, 0), (-1, -1), font_size + 1.0),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3.2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3.2),
            ("TOPPADDING", (0, 0), (-1, -1), 2.3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.3),
        ]))
        return table

    def _warning_box(self, text, style, width=None):
        """Render a warning as a real table block so it cannot collide with nearby paragraphs."""
        width = width or (A4[0] - 0.64 * inch)
        safe_text = str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        table = Table([[Paragraph(safe_text, style)]], colWidths=[width], hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff4e5")),
            ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#d97706")),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        return table

    def export_pdf(self):
        try:
            if not REPORTLAB_AVAILABLE:
                messagebox.showerror(
                    "Missing PDF Dependency",
                    "PDF export requires reportlab. Install it on Windows with:\n\npy -m pip install reportlab",
                )
                return

            m = self.perform_math()
            path = filedialog.asksaveasfilename(
                defaultextension=".pdf",
                filetypes=[("PDF files", "*.pdf")],
                title="Save G/T Measurement Report",
            )
            if not path:
                return

            doc = SimpleDocTemplate(
                path,
                pagesize=A4,
                rightMargin=0.32 * inch,
                leftMargin=0.32 * inch,
                topMargin=0.30 * inch,
                bottomMargin=0.30 * inch,
                title="G/T Measurement",
            )
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                "ReportTitle",
                parent=styles["Title"],
                fontName="Helvetica-Bold",
                fontSize=14,
                leading=15,
                spaceAfter=3,
            )
            subtitle_style = ParagraphStyle(
                "ReportSubtitle",
                parent=styles["BodyText"],
                fontSize=8.4,
                leading=9.6,
                textColor=colors.HexColor("#333333"),
                spaceAfter=2,
            )
            h_style = ParagraphStyle(
                "ProfessionalHeading",
                parent=styles["Heading2"],
                fontName="Helvetica-Bold",
                fontSize=10.2,
                leading=11.4,
                spaceBefore=5,
                spaceAfter=3,
            )
            subheading_style = ParagraphStyle(
                "ProfessionalSubheading",
                parent=styles["BodyText"],
                fontName="Helvetica-Bold",
                fontSize=8.8,
                leading=10.0,
                textColor=colors.HexColor("#1f4e79"),
                spaceBefore=3,
                spaceAfter=1,
            )
            body_style = ParagraphStyle(
                "ProfessionalBody",
                parent=styles["BodyText"],
                fontSize=8.2,
                leading=10.0,
                spaceAfter=2,
            )
            formula_style = ParagraphStyle(
                "FormulaBody",
                parent=styles["BodyText"],
                fontName="Courier",
                fontSize=7.4,
                leading=8.8,
                leftIndent=8,
                textColor=colors.HexColor("#222222"),
                spaceAfter=1.3,
            )
            warning_style = ParagraphStyle(
                "WarningBody",
                parent=styles["BodyText"],
                fontName="Helvetica-Bold",
                fontSize=8.0,
                leading=10.0,
                textColor=colors.HexColor("#9a3412"),
                spaceBefore=0,
                spaceAfter=0,
            )
            mono_style = ParagraphStyle(
                "CompactMono",
                parent=styles["BodyText"],
                fontName="Courier",
                fontSize=6.0,
                leading=6.8,
                spaceAfter=0.7,
            )

            def draw_report_footer(canvas, doc_obj):
                """Draw small italic developer/license notice at the lower edge of every PDF page."""
                canvas.saveState()
                canvas.setFont("Helvetica-Oblique", 6.5)
                canvas.setFillColor(colors.HexColor("#666666"))
                footer_text = self.LICENSE_FOOTER_TEXT
                page_text = f"Page {doc_obj.page}"
                y_pos = 0.16 * inch
                canvas.drawString(doc_obj.leftMargin, y_pos, footer_text)
                canvas.drawRightString(A4[0] - doc_obj.rightMargin, y_pos, page_text)
                canvas.restoreState()

            story = []
            story.append(Paragraph("G/T Measurement", title_style))
            story.append(Paragraph(f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S}", subtitle_style))
            story.append(Paragraph(f"Solar flux source: {m['source_url']}", subtitle_style))
            story.append(Paragraph("Bold parameter names identify direct inputs to the final G/T equation: k, y, S_rx, lambda, and L.", subtitle_style))
            story.append(Spacer(1, 5))
            if m["data_validity_status"] != "LIVE_NOAA_CURRENT":
                story.append(self._warning_box(m["data_warning"], warning_style))
                story.append(Spacer(1, 6))

            key_styles = [
                ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#d9eaf7")),
                ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
            ]
            story.append(Paragraph("Key Result and Data Source Summary", h_style))
            story.append(self._compact_table(
                self.get_key_result_rows(m),
                col_widths=[1.75 * inch, 0.95 * inch, 4.90 * inch],
                styles=key_styles,
                paragraph_cols={0, 2},
                font_size=7.7,
            ))

            story.append(Spacer(1, 4))
            first_page_tables = [
                Paragraph("Direct Inputs to the Final G/T Equation", h_style),
                self._compact_table(
                    self.get_direct_gt_input_rows(m),
                    col_widths=[1.90 * inch, 0.70 * inch, 1.50 * inch, 3.40 * inch],
                    styles=[],
                    paragraph_cols={0, 3},
                    font_size=7.8,
                    bold_first_col_values=self.DIRECT_GT_PARAMETERS,
                ),
                Spacer(1, 4),
                Paragraph(f"{m['station']} Solar Radio Flux Values Used", h_style),
                self._compact_table(
                    self.get_spectrum_rows(m),
                    col_widths=[1.25 * inch, 1.45 * inch, 1.20 * inch, 3.35 * inch],
                    styles=[],
                    paragraph_cols={2, 3},
                    font_size=7.7,
                ),
            ]
            story.extend(first_page_tables)

            story.append(PageBreak())
            story.append(Paragraph("Full Traceability Audit Tables", h_style))
            story.append(Paragraph("The long audit table is split into sections so the report remains readable in A4 portrait format.", body_style))
            for title, table_rows in self.get_traceability_sections(m):
                section_block = [
                    Paragraph(title, subheading_style),
                    self._compact_table(
                        table_rows,
                        col_widths=[1.85 * inch, 0.75 * inch, 1.05 * inch, 3.95 * inch],
                        styles=[("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#eaf3fb"))] if title == "Final G/T Equation Values" else [],
                        paragraph_cols={0, 3},
                        font_size=7.0,
                        bold_first_col_values=self.DIRECT_GT_PARAMETERS,
                    ),
                    Spacer(1, 4),
                ]
                # Keep smaller sections together; allow large sections to split only by row.
                if len(table_rows) <= 12:
                    story.append(KeepTogether(section_block))
                else:
                    story.extend(section_block)

            ranking_block = [
                Paragraph("RSTN Station Distance Ranking", h_style),
                self._compact_table(
                    self.get_station_ranking_rows(m),
                    col_widths=[0.50 * inch, 1.35 * inch, 3.60 * inch, 1.00 * inch],
                    styles=[],
                    paragraph_cols={2},
                    font_size=7.4,
                ),
            ]
            story.append(KeepTogether(ranking_block))

            story.append(PageBreak())
            self._add_pdf_line_section(
                story,
                "Engineering Methodology and Traceability",
                self.get_explanation(),
                h_style,
                body_style,
                subheading_style,
                formula_style,
            )

            story.append(PageBreak())
            self._add_pdf_line_section(
                story,
                "Mathematical Formulation Details",
                self.get_formula_details(),
                h_style,
                body_style,
                subheading_style,
                formula_style,
            )

            story.append(Spacer(1, 4))
            story.append(PageBreak())
            story.append(Paragraph("Software Credit and MIT License", h_style))
            story.append(Paragraph(self.LICENSE_FOOTER_TEXT, body_style))
            story.append(Paragraph(self.COPYRIGHT_TEXT, body_style))
            story.append(Spacer(1, 4))
            self._add_pdf_line_section(
                story,
                "Full MIT License Text",
                self.get_license_report_lines(),
                h_style,
                mono_style,
                subheading_style,
                mono_style,
            )

            story.append(PageBreak())
            story.append(Paragraph("Raw NOAA Rows / Manual Solar Flux Source Note", h_style))
            for line in m["raw_noaa"]:
                story.append(Paragraph(str(line), mono_style))

            doc.build(story, onFirstPage=draw_report_footer, onLaterPages=draw_report_footer)
            messagebox.showinfo("Success", f"G/T Measurement report exported:\n{path}")
        except Exception as exc:
            messagebox.showerror("Export Error", str(exc))


def main():
    root = tk.Tk()
    GTStationApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()


# MIT License Notice
# Copyright (c) 2026 Wahyudi Hasbi
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
