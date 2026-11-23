# Building a Windows EXE with GitHub Actions

1. Create a GitHub repository and upload the **contents of this ZIP**, keeping `.github/workflows/build-windows.yml` in its folder. The repository root must contain `app.py` and `requirements.txt`.
2. In GitHub, select **Actions > Build SolarCharge Windows EXE > Run workflow** (or push to `main`).
3. After the build succeeds, open its run page and download **SolarCharge-Windows** under **Artifacts**. Extract the ZIP to get `SolarCharge.exe`.
4. Double-click `SolarCharge.exe`, keep the console window open, and visit `http://127.0.0.1:8080` in your browser. Closing the console stops the app.

The executable runs in **simulation mode** unless you separately configure the meter bridge and Tesla credentials. Do not place API tokens or `.env` secrets in your GitHub repository. The provided starter does not load `.env` automatically. Do not enable unattended real charging without validating safety interlocks, actual car telemetry, and access controls. The dashboard is bound to localhost.
