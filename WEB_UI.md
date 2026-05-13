# Gatekeeper Battery Edition Web UI

The web UI is part of GatekeeperV2 Battery Edition. It starts with the bot and gives you browser-based control over AMP servers, Discord embeds, banners, whitelist settings, permissions, users, regex settings, and bot credentials.

## Transparency

AI assistance was used while creating and modifying parts of Battery Edition, including web UI code, documentation, and troubleshooting changes. Please review and test changes before using them in production.

## Start With AMP

The recommended launch path is AMP Python App Runner:

```text
App Run Mode: Python script
App Script Filename: start.py
Python Packages Install Method: Requirements.txt file
```

Gatekeeper will use AMP's assigned `GenericModule.App.Ports.$ApplicationPort1` value when AMP provides it.

For the most reliable AMP setup, add the assigned port template to App Command Line Arguments:

```text
-super --web-port {{$ApplicationPort1}}
```

If you do not use `-super`, use:

```text
--web-port {{$ApplicationPort1}}
```

AMP should substitute that into the actual assigned port before launching Python.

Do not use `{{$ServerPort}}` for the web UI unless your AMP template maps that to the exposed web port. In some templates it is an app/game port such as `7777`.

Gatekeeper also checks AMP's `AMPConfig.conf` and prefers `AMP.PrimaryEndpoint` or the monitor port named Main Port when those files are readable.

Example URL:

```text
http://192.168.4.107:40004
```

## Start Locally

For local testing:

```powershell
python -m pip install -r requirements.txt
python start.py --web-port 40004
```

Then open:

```text
http://127.0.0.1:40004
```

## First Login

Fresh installs do not use a default username or password.

On first page load, the web UI asks you to create the first web account. Existing installs that already have a `web_config.json` keep using their saved account.

Do not commit `web_config.json`; it contains install-specific login data and is ignored by git.

## Reset Login

To reset the web UI login, stop the bot and run:

```powershell
python start.py --reset-web-login
```

In AMP, temporarily use this as App Command Line Arguments:

```text
--reset-web-login
```

Start the instance once, let it exit, then restore your normal App Command Line Arguments and start Gatekeeper again. The web UI will show first-time login setup.

## Credentials

Use the AMP Login / Credentials page to manage:

- Discord bot token.
- AMP URL.
- AMP username.
- AMP password.
- AMP 2FA/TOTP secret when needed.

Secret fields are blank when the page loads. Leaving a secret field blank keeps the saved value.

## What It Controls

- AMP server start, stop, restart, kill, backup, and console message actions when AMP is connected.
- Live AMP connected, container online, dedicated server online, and starting status.
- Automatic removal of servers from the web panel when AMP no longer reports the instance.
- Server display mode: embed or banner.
- Discord posting destinations for embed/banner updates.
- Discord embed fields, colors, emojis, footer timezone, uploaded images, and thumbnails.
- Banner settings and uploaded banner images.
- Bot-wide settings exposed by the Gatekeeper configuration system.
- Permission groups with friendly names.
- Discord users and assigned Gatekeeper roles.
- Regex patterns and server assignments.
- Whitelist request settings and response messages.
- Dark and light mode.

If AMP is not connected, the UI still allows database-backed configuration pages to load where possible.

Stale server cleanup is skipped when AMP returns no instances, because that usually means a permission or connection problem rather than every server being removed.

Whitelist request buttons collect Minecraft IGN for Minecraft servers and SteamID64 for every non-Minecraft server, including Steam games using AMP generic configs. Non-Minecraft games are routed to staff approval instead of attempting unsupported direct whitelist-file edits.
