# GatekeeperV2 Battery Edition

GatekeeperV2 Battery Edition is a fork of the original GatekeeperV2 Discord bot by k8thekat.

This fork is focused on making Gatekeeper usable from a web panel instead of relying only on Discord commands. It keeps the AMP and Discord bot foundation from GatekeeperV2, then adds a mobile-friendly web UI, first-run setup, live previews, image uploads, server controls, permission management, and AMP-friendly launch behavior.

## Transparency Notice

AI assistance was used while creating and modifying parts of GatekeeperV2 Battery Edition, including code changes, web UI work, documentation, and troubleshooting support.

AI-assisted changes should still be reviewed, tested, and maintained like any other code. Community reports, human review, and real AMP/Discord testing remain important before relying on this fork in production.

Primary fork repository:

```text
https://github.com/BatteryVoltic/GatekeeperV2-batteryedition.git
```

Original project:

```text
https://github.com/k8thekat/GatekeeperV2
```

## What This Bot Does

GatekeeperV2 Battery Edition connects Discord to CubeCoders AMP so you can manage game servers, whitelist requests, server status posts, embeds, banners, permissions, and users from one place.

The bot still supports Discord-side commands, but this fork adds a web UI so normal configuration work can be done without memorizing commands or developer field names.

## Battery Edition Changes

This fork adds or reworks the following areas:

| Area | What changed |
| --- | --- |
| Web UI | Flask web panel launches with `start.py` and runs on the AMP assigned port. Local runs fall back to `40004`. |
| First-time setup | Fresh installs require creating a web login. The old default `admin` / `admin` login is not used for new installs. |
| AMP and Discord credentials | The web UI includes settings for the Discord bot token and AMP token file values. |
| AMP App Runner support | The bot reads AMP assigned ports such as `GenericModule.App.Ports.$ApplicationPort1`. |
| Live server status | Overview and server pages show AMP connected, container online, server online, and starting states. |
| Removed AMP servers | Servers removed from AMP are automatically removed from the web panel after AMP sync confirms they no longer exist. |
| Discord embeds | Embed settings have live preview, status colors, emojis, footer timezone formatting, image upload, and thumbnail upload/editor support. |
| Discord banners | Banner settings are separated from embed settings and use the same posting/channel system where applicable. |
| Embed or banner mode | A server can use embed mode or banner mode. The UI shows the matching settings for the selected mode. |
| Image uploads | Uploaded images can be selected for embed images, embed thumbnails, and banners. |
| Whitelist requests | Whitelist-enabled servers can show a Discord button so users can request whitelist access through a form. |
| Permissions | Permission editing uses friendly names, categories, and a separate Users page for assigning roles. |
| Discord users | On bot startup and when users join, non-bot Discord users can be registered with the default General role. |
| Reboot button | The web UI can trigger a bot reboot. In AMP this depends on the instance being configured to restart after exit. |
| Console cleanup | Web request spam is reduced and shutdown logging is clearer. |

## Requirements

Before installing, you need:

| Requirement | Notes |
| --- | --- |
| CubeCoders AMP | Recommended install target for this fork. |
| Python App Runner instance | Use Python `3.11`. |
| Discord bot token | Create this in the Discord Developer Portal. |
| Discord privileged intents | Enable Server Members Intent and Message Content Intent for the bot. |
| AMP user account | Use a dedicated AMP user for Gatekeeper. |
| AMP permissions | The AMP user must have permission to view and control the instances you want Gatekeeper to manage. |
| Open TCP port | The web UI needs the AMP assigned web port open, for example `40004`. |

UDP is not required for the web UI. The browser connects over TCP.

## Recommended AMP Setup

These steps are written for AMP's Python App Runner.

### 1. Create The AMP Instance

1. Open AMP.
2. Create a new instance.
3. Choose Python App Runner.
4. Start with Python `3.11`.

### 2. Configure The Download Tab

Use these values on the AMP Download tab:

| AMP setting | Value |
| --- | --- |
| App Download Type | `Git repo` |
| App Download Source | `https://github.com/BatteryVoltic/GatekeeperV2-batteryedition.git` |
| Git Repo Branch | Leave blank unless you need a specific branch. |
| Git Repo Username | Leave blank for the public repo. |
| Git Repo Password/Token | Leave blank for the public repo. |
| GitHub Release Filename | Not used for Git repo installs. |
| GitHub Release Version | Not used for Git repo installs. |
| PyPI Package Installation Arguments | `--force-reinstall --no-cache-dir` |

After changing the Download tab, run AMP's download/update action for the instance.

### 3. Configure The App Tab

Use these values on the AMP App tab:

| AMP setting | Value |
| --- | --- |
| Run App Setup Command | Off |
| App Setup Command | Leave blank |
| Python Version | `3.11` |
| Python Packages Install Method | `Requirements.txt file` |
| Specific Python Package Requirements | Leave blank when using the requirements file. |
| App Run Mode | `Python script (default)` |
| App Script Filename | `start.py` |
| App Module Name | Leave blank |
| App Subdirectory | Leave blank |
| App Environment Variables | Optional. Normally leave blank. |
| App Command Line Arguments | `-super --web-port {{$ApplicationPort1}}` |

If you do not need `-super`, use this instead:

```text
--web-port {{$ApplicationPort1}}
```

Do not hard-code the web UI port in AMP unless you are intentionally testing outside AMP's assigned port system.

## AMP Web Port Setup

Gatekeeper Battery Edition uses AMP's assigned application port for the web UI. AMP stores that setting as:

```text
GenericModule.App.Ports.$ApplicationPort1
```

AMP does not always pass that value to the Python process automatically. The reliable setup is to add this to AMP's App Command Line Arguments:

```text
--web-port {{$ApplicationPort1}}
```

If you also use super-user startup behavior:

```text
-super --web-port {{$ApplicationPort1}}
```

After AMP substitutes the value, Gatekeeper receives something like:

```text
--web-port 40004
```

Gatekeeper also understands AMP-style arguments if AMP provides them directly:

```text
+GenericModule.App.Ports.$ApplicationPort1 40004
```

The web UI port is chosen in this order:

1. `--web-port <port>` command line argument.
2. AMP's `AMP.PrimaryEndpoint` in `AMPConfig.conf`, when readable.
3. AMP's `Monitoring.MonitorPorts` entry named Main Port, when readable.
4. AMP assigned `GenericModule.App.Ports.$ApplicationPort1`.
5. Supported AMP/web port environment variables.
6. Nearby AMP config files, when readable.
7. AMP `ServerPort` only as a last AMP-port fallback.
8. Local fallback port `40004` when not running in AMP.

Do not use `{{$ServerPort}}` for the web UI in AMP unless your Python App Runner template specifically maps that to the exposed web port. On many AMP templates, `ServerPort` can be an app/game port such as `7777`, while `ApplicationPort1` is the exposed port shown on the AMP page.

If your AMP instance is assigned port `40004`, open:

```text
http://SERVER-IP:40004
```

Example:

```text
http://192.168.4.107:40004
```

If the page does not load, check these items first:

1. AMP assigned the port you expect.
2. The instance is actually running.
3. The firewall allows TCP on that port.
4. You are using `http://`, not `https://`.
5. The console shows `Gatekeeper Web UI listening on http://0.0.0.0:<port>`.
6. AMP App Command Line Arguments include `--web-port {{$ApplicationPort1}}`.

## First Startup

On a fresh install:

1. Start the AMP instance.
2. Open the web UI in your browser.
3. Create the first web UI login.
4. Open AMP Login / Credentials in the web UI.
5. Enter the Discord bot token and AMP login details.
6. Save the credentials.
7. Reboot the bot from the web UI or restart the AMP instance.

Secret fields are intentionally blank when the page loads. Leaving a secret field blank keeps the saved value.

## Reset Web Login

If you need to recreate the web UI login, stop the bot and run:

```powershell
python start.py --reset-web-login
```

In AMP, temporarily set App Command Line Arguments to:

```text
--reset-web-login
```

Start the instance once. The command resets the web login and exits. Then restore your normal App Command Line Arguments, start Gatekeeper again, and open the web UI. It will ask you to create a new login.

## Discord Bot Setup

In the Discord Developer Portal:

1. Create an application.
2. Create a bot user.
3. Copy the bot token.
4. Enable Server Members Intent.
5. Enable Message Content Intent.
6. Invite the bot to your Discord server with the permissions needed for channels, messages, embeds, buttons, and member lookup.

After the bot is online, sync commands if needed:

```text
$bot utils sync
```

Depending on your command setup, slash command syncing may also be available from Discord.

## Web UI Sections

| Section | Purpose |
| --- | --- |
| Overview | Quick server list, status dots, recent changes, and live server state. |
| Servers | Per-server settings and server-specific Discord posting controls. |
| Display | Global display behavior, update intervals, and embed/banner mode controls. |
| Permissions | Role and permission editing using friendly names and grouped categories. |
| Users | Discord user role assignment. Non-bot users can be registered automatically. |
| AMP Login / Credentials | Discord token and AMP login/token settings. |
| Regex | Regex configuration for supported server modules. |
| Whitelist | Whitelist settings and response text where supported. |
| Bot Settings | Bot-level options exposed by the existing Gatekeeper configuration system. |

Settings are designed to autosave when changed. You should not need to press a save button for normal toggles and simple fields.

When AMP no longer reports a server instance, Gatekeeper removes that server from the web panel and related web UI assignments. If AMP returns no instances because of a permission or connection problem, cleanup is skipped to avoid deleting valid servers by mistake.

## Embed And Banner Posting

Each server can use either embed mode or banner mode.

| Mode | Behavior |
| --- | --- |
| Embed | Posts and updates a Discord embed with status fields, colors, footer time, images, and thumbnail options. |
| Banner | Posts and updates a banner image/status display. |

Only one mode should be active per server. Shared posting settings, such as where to post in Discord, apply to the selected mode.

### Embed Features

Embed settings include:

- Discord post destination.
- Dedicated server status text.
- Status emojis.
- Embed color by dedicated server status.
- Custom hex colors.
- Optional hidden fields such as Donators Only and Whitelist Open.
- Embed image upload and selection.
- Embed thumbnail upload and selection.
- Thumbnail crop/editor tools.
- Footer timezone selector.
- Live Discord-style preview.

The embed color follows the dedicated server status, not only the AMP container status. This allows starting, online, and offline states to use different colors.

### Footer Timezone

The global display timestamp can use Discord's timestamp format, for example:

```text
<t:1778462820:f>
```

For embed footers only, Battery Edition also supports a readable server-specific footer date/time using a selected timezone.

The timezone selector lists common timezones in timezone order with UTC offsets. Typing into the field jumps/searches through the list.

## Discord API Update Intervals

Discord rate limits can change and are enforced by Discord. As a practical default:

- Avoid very low intervals.
- Use `60` seconds or higher when you have multiple servers or multiple posting groups.
- Use `30` seconds only for small setups.
- Avoid going below `15` seconds unless you know exactly how many messages the bot updates.

Gatekeeper should post in the time frame you choose unless the interval would create rate-limit problems.

## Whitelist Requests

For whitelist-enabled servers, users can request whitelist access from a Discord button on the server listing.

When clicked:

1. Discord opens a form.
2. The user's Discord ID and name are captured automatically by Discord.
3. Minecraft servers ask for Minecraft IGN and use the Minecraft whitelist handler.
4. Every non-Minecraft server asks for SteamID64 and includes a SteamID64 lookup link in the form. This includes Steam games using AMP generic configs.
5. The request is posted to the configured whitelist request channel.

Only Minecraft currently has direct server-side whitelist file handling in this fork. Non-Minecraft games are supported through the request/approval workflow using SteamID64 so Steam-based servers are handled consistently, including servers that AMP reports through generic configs.

If users see this message:

```text
It appears the Staff has yet to setup a Whitelist Request Channel.
```

configure the whitelist request channel for that server in the web UI.

## Permissions And Users

Permissions are grouped by friendly categories so they are easier to understand than raw developer permission names.

Users are managed separately from permissions because large Discord servers can make a combined page too long. Use the Users page to assign roles to registered Discord users.

Battery Edition can automatically register non-bot Discord members:

- On bot startup.
- When a new non-bot user joins the Discord server.

New users receive the default General role.

## AMP Permissions

Gatekeeper needs enough AMP permissions to see and control the instances you assign to it.

If the console says a permission is missing, add that permission to the AMP user used by Gatekeeper.

Example:

```text
Gatekeeper is missing the permission __LocalFileBackup.*__
```

Fix this in AMP:

```text
Configuration -> User Management -> gatekeeper user -> Permissions
```

Then restart the Gatekeeper instance.

## Local Development Run

For local testing outside AMP:

```powershell
python -m pip install -r requirements.txt
python start.py --web-port 40004
```

Then open:

```text
http://127.0.0.1:40004
```

## Useful Startup Arguments

| Argument | Purpose |
| --- | --- |
| `--web-port 40004` | Manually sets the web UI port. |
| `--reset-web-login` | Resets the web UI login setup and exits. The next web page load asks for a new login. |
| `-super` | Starts with super-user behavior used by existing Gatekeeper workflows. |
| `-token` | Legacy token setup behavior. The web credentials page is preferred for normal setup. |
| `-dev` | Development mode used by existing Gatekeeper workflows. |
| `-debug` | Enables debug behavior where supported. |
| `-discord` | Discord-related startup behavior from the original bot. |
| `-command` | Command mode from the original bot. |

## Rebooting From The Web UI

The web UI includes a reboot button.

This tells the bot process to exit. In AMP, the instance must be configured to restart the app if you want it to come back automatically. If AMP is not configured to restart it, press Start in AMP again.

## Troubleshooting

### The web page does not load

Check:

- The AMP instance is running.
- The console says the web UI is listening.
- The IP and port are correct.
- The port is open for TCP.
- The URL starts with `http://`.
- AMP assigned the expected `ApplicationPort1`.

### The bot cannot log into Discord

Check:

- The Discord token is saved in the web credentials page.
- The bot token was copied correctly.
- The bot has been invited to the Discord server.
- Required privileged intents are enabled.
- Restart the bot after changing the token.

### AMP servers do not show correctly

Check:

- AMP URL, username, password, and optional 2FA secret are saved.
- The AMP user has access to the target instances.
- The AMP user has the required permissions.
- Restart the bot after changing AMP credentials.

### Server shows starting or online incorrectly

Battery Edition tracks AMP container state and dedicated server state separately. If status looks wrong:

- Check the AMP instance state.
- Check whether the dedicated server is still starting.
- Wait for the next configured update interval.
- Confirm the server module reports status correctly.

### Embed or banner did not update

Check:

- The server is set to the correct display mode.
- The Discord post destination is configured.
- The bot can send and edit messages in that channel.
- The update interval is not too low.
- The selected image still exists.

## Credits

GatekeeperV2 Battery Edition is a fork of GatekeeperV2 by k8thekat.

Battery Edition changes and web UI work are maintained for:

```text
https://github.com/BatteryVoltic/GatekeeperV2-batteryedition.git
```
