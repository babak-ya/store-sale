# Install and run StoreSale

Use this guide for the current source-code version. For Persian instructions, see
[INSTALL_FA.md](INSTALL_FA.md).

**This is a prototype for test data.** Login, products, opening stock and backups are
available; checkout, credit and returns are still under development. See
[STATUS.md](STATUS.md). There is no standalone Windows installer yet. Automated
validation was performed on Linux; a clean Windows installation has not been certified.

## 1. What you need

- Python **3.12** (the project currently requires this minor version).
- A browser such as Edge, Chrome or Firefox.
- Internet for the initial Python/package downloads. Runtime works offline.
- VS Code is convenient but optional. Git, Node and Docker are not required.

On Windows, download Python 3.12 from [python.org](https://www.python.org/downloads/windows/).
Include the Python launcher (`py`) during installation. Reopen your terminal afterward.

## 2. Download and open the project

1. Open [the GitHub repository](https://github.com/babak-ya/store-sale).
2. Select the `main` branch, then **Code → Download ZIP**.
3. Right-click the downloaded ZIP → **Extract All**. Do not run files inside the ZIP.
4. Move the extracted project to a local folder, for example
   `C:\StoreSale\store-sale-main`. Avoid OneDrive or a network share.
5. In VS Code, select **File → Open Folder** and open the folder containing
   `requirements.lock`, `alembic.ini`, and the `app` folder. Choose
   **Terminal → New Terminal**, using **PowerShell** on Windows.

Without VS Code, open PowerShell and change to your extracted folder:

```powershell
cd "C:\StoreSale\store-sale-main"
```

Replace that example path with your actual folder. All following commands run there.

## 3. Windows: first installation

Run each command separately. If one reports an error, stop and resolve it before
continuing. Verify Python first:

```powershell
py -3.12 --version
```

The result should start with `Python 3.12`. Then create the local Python environment
and install the pinned packages:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip check
```

`pip check` should print `No broken requirements found`. You do not need to activate
the environment or change PowerShell execution policy.

Select the standard local data folder and initialize the database:

```powershell
$env:STORE_DATA_DIR = "$env:LOCALAPPDATA\StoreSale"
$env:STORE_PORT = "8765"
.\.venv\Scripts\alembic.exe upgrade head
```

The migration may complete silently. Confirm the installation with:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The current suite should pass (41 tests at the time of writing). It uses temporary
databases, so it does not create accounts in your application database. One known
TestClient deprecation warning is documented in STATUS.md.

## 4. Start and create your account

```powershell
.\.venv\Scripts\python.exe -m app
```

Keep the terminal open. The browser should open; if it does not, enter
**http://127.0.0.1:8765** in its address bar. Use that exact address, including `http`
and `127.0.0.1`. If the page opens before startup finishes, refresh it after a moment.

On first use, create your manager account:

- Username: 3–50 characters.
- Password: 12–128 characters. Choose your own; there is no default password.
- After creating it, sign in on the login page.

Account creation should take you to login, and login should show the Persian dashboard.
For a functional check, define a synthetic counted product with step `1`, price
`10` toman and price basis `1`. Register an opening quantity of `3`, total value
`15` toman and a test reason. The table should show `3` counts and `15` toman value.
Do not use real customer or sales data in this prototype.

## 5. Stop and launch later

To stop, click the running terminal and press **Ctrl+C**. Closing the browser alone
does not stop the server. A second launch on the same port opens the existing app.

For later launches, open a terminal in the same project folder and run:

```powershell
$env:STORE_DATA_DIR = "$env:LOCALAPPDATA\StoreSale"
$env:STORE_PORT = "8765"
.\.venv\Scripts\python.exe -m app
```

You do not need to recreate `.venv` or repeat first-time installation. The environment
variables above apply only to that terminal. If you choose a custom data folder or
port, use the same values on every launch. The default data folder is also
`%LOCALAPPDATA%\StoreSale` when no override is set.

## 6. Data, backups and updates

The dashboard shows the data folder. It contains `store.sqlite3` and a `backups`
subfolder. Keep it on a local disk, outside the downloaded code. Do not delete it when
replacing the application folder.

Use the manager's **ساخت پشتیبان بررسی‌شده** button. Successful completion creates a
consistent snapshot and a matching `.json` manifest. Copy both to an external disk
for protection against failure of the computer's disk. Do not copy just the live
`store.sqlite3` file while the app runs. Production restore is not implemented yet.

For source updates, create a backup, stop the app, then download the latest `main`
ZIP into a **new** folder. Repeat installation there using the same data folder.
Read the release/status notes first: this version supports schema `0001` only;
future schema changes require their own tested upgrade instructions. Do not delete
the database to work around an upgrade error.

## 7. Troubleshooting

| Message or symptom | What to do |
| --- | --- |
| `py` is not recognized | Install Python 3.12 with its launcher and reopen the terminal. If the launcher is unavailable but `python --version` reports 3.12, use `python` instead of `py -3.12` for the two initial commands. |
| `No suitable Python runtime found` | Install Python 3.12; another Python version alone is insufficient. |
| `requirements.lock` not found, or `No module named app` | Open the project folder containing `requirements.lock` and `app`, then retry there. |
| `.venv\Scripts\python.exe` not found | Create `.venv` in that project folder. Do not reuse a virtual environment copied from another computer or Linux. |
| Package download/TLS failure | Check internet, proxy and the system date. Do not disable certificate verification. Keep the error text for diagnosis. |
| `Origin نامعتبر` during account creation | Use the latest GitHub version and the exact local address above. An old version sent `Referrer-Policy: no-referrer`; the current file `app/web/application.py` uses `same-origin`. Restart the app and refresh the form after updating. |
| `Host نامعتبر` | Use `http://127.0.0.1:8765`, not `localhost`, a computer name or a LAN IP. |
| Invalid/expired form message | Refresh the page and submit again with browser cookies enabled. |
| Port occupied, but no healthy StoreSale instance found | Another app may use 8765. Set `$env:STORE_PORT = "8766"`, launch again, and use `http://127.0.0.1:8766`. Keep that port for later launches. |
| Browser says connection refused | Check that the app command is still running without an error. Wait briefly and refresh. |
| A new setup screen appears instead of your existing account | Stop and check that the same Windows account and `STORE_DATA_DIR` are being used. Do not create a replacement account until the original data path is located. |

If a step fails, share the failing command and error text. Do not share passwords,
session cookies, database files or real customer/card data.

## Linux / Codex cloud alternative

From the extracted project folder with Python 3.12 installed:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip check
export STORE_DATA_DIR="$HOME/.local/share/StoreSale"
export STORE_PORT=8765
.venv/bin/alembic upgrade head
.venv/bin/python -m pytest -q
.venv/bin/python -m app --no-browser
```

If `python3 --version` reports 3.12, it can replace `python3.12` in the first command.
On your own Linux computer, open the local address in a browser. In Codex cloud,
the onboarding UI has no browser preview: the app can run and be tested there, but
its loopback address is not reachable through your computer's browser.
