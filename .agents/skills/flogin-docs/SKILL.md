---
name: flogin-docs
description: Comprehensive offline documentation and guide for the `flogin` Python library (Flow Launcher V2 JSON-RPC API framework). Use this skill whenever building, refactoring, configuring settings, writing search handlers, handling events, or testing Flow Launcher Python plugins.
---

# flogin Documentation & Skill Guide

`flogin` is a modern, fully-typed, asynchronous Python wrapper for Flow Launcher's V2 JSON-RPC API. It runs a single persistent process during Flow Launcher's lifespan for high performance and low memory overhead.

---

## Workspace Documentation Structure

The local documentation directory contains converted Markdown documentation files. Use the map below to load specific files into context depending on the task:

| Topic / Requirement | Target File to Inspect | Description |
| :--- | :--- | :--- |
| **Getting Started & Overview** | `intro.md` | Requirements (Python 3.11+), installation commands, and core concepts. |
| **Quickstart & Setup** | `quickstart.md` | Minimal plugin example (`main.py`), `sys.path` bootstrapping, and `plugin.json` schema. |
| **API Reference** | `api.md` | Complete class/method specification (`Plugin`, `Query`, `Result`, `FlowLauncherAPI`, `Pip`, etc.). |
| **Search & Query Handlers** | `search_handlers.md` | Registering `@plugin.search()`, conditions (`PlainTextCondition`, `RegexCondition`), error handling, and caching. |
| **Event Lifecycle** | `events.md` | API events (`on_initialization`, `on_close`) and global error handling (`on_error`). |
| **Plugin Settings** | `settings.md` | Creating `SettingsTemplate.yaml`, accessing typed `Plugin.settings`, and `Settings` subclassing. |
| **Testing & Mocking** | `testing.md` | Unit testing plugins with `PluginTester`, mocking `FlowLauncherAPI`, and `pytest-asyncio` setups. |
| **Complex Plugin Architecture** | `complex_plugins.md` | Splitting handlers across multiple files and using `py -m flogin init`. |
| **Logging & Debugging** | `log-override-files.md` | Overriding logs using `.flogin.debug` and `.flogin.prod` trigger files. |
| **Installation Methods** | `install_plugin.md` | Manual installation into Flow's `UserData/Plugins` directory and installing via ZIP (`pm install`). |
| **FAQ & Troubleshooting** | `faq.md` | Asynchronous coroutines, non-blocking code guidelines, title highlighting, and API V1 vs V2 differences. |
| **Library Versioning** | `version_guarantees.md` | Semantic versioning guarantees and breaking vs non-breaking API changes. |
| **Changelog** | `whats_new.md` | Detailed changes across versions (v2.0.0, v1.1.0, etc.). |

---

## Core Development Rules for `flogin`

When writing code using `flogin`, strictly adhere to these framework rules:

### 1. Project Configuration (`plugin.json`)
Every `flogin` plugin requires a `plugin.json` file in the root folder:
* Set `"Language": "python_v2"` (mandatory for V2 JSON-RPC API).
* Set `"ExecuteFileName"` to your main entry point (e.g., `main.py`).
* Generate a valid 32-bit UUID for `"ID"`.

### 2. Main Entry Point (`main.py`) & Path Setup
Flow Launcher does not automatically run plugins inside your virtual environment. Always place `sys.path` additions at the very top of your execution entry file before importing `flogin`:

```python
import os
import sys

parent_folder_path = os.path.abspath(os.path.dirname(__file__))
sys.path.append(parent_folder_path)
sys.path.append(os.path.join(parent_folder_path, "lib"))
sys.path.append(os.path.join(parent_folder_path, "venv", "lib", "site-packages"))

from flogin import Plugin, Query, Result

plugin = Plugin()
```

### 3. Asynchronous Execution & Non-Blocking Rules
* All search handlers and event callbacks **must be `async def` coroutines**.
* **Never use blocking calls** like `time.sleep()` or synchronous HTTP clients like `requests.get()` inside handlers. Use `asyncio.sleep()` and `aiohttp.ClientSession()` instead.

### 4. Search Handler Conventions
* Decorate search functions using `@plugin.search()`.
* Handler callbacks accept a `data: Query` parameter.
* Handlers can return/yield a `Result`, a list of `Result` objects, `dict`, `str`, or `int` (which `flogin` automatically converts into `Result` instances).

```python
@plugin.search()
async def query_handler(query: Query):
    return Result(
        title=f"Query: {query.text}",
        sub="Press Enter to copy",
        copy_text=query.text
    )
```

### 5. Accessing Flow Launcher API
Use `plugin.api` to interact with Flow Launcher (e.g., `plugin.api.show_notification()`, `plugin.api.open_url()`, `plugin.api.fuzzy_search()`).

---

## Quick Task Guidance Matrix

* **Need to create custom settings GUI?** Read `settings.md` to format `SettingsTemplate.yaml` and subclass `flogin.Settings`.
* **Need to test handlers without launching Flow?** Read `testing.md` to use `PluginTester` and mock `FlowLauncherAPI`.
* **Need conditional routing (e.g., regex/plain text matching)?** Read `search_handlers.md` for `PlainTextCondition`, `RegexCondition`, `KeywordCondition`, `AnyCondition`, and `AllCondition`.
* **Need caching for fast responses?** Read `search_handlers.md` and `api.md` for `@cached_coro`, `@cached_gen`, and `clear_cache()`.
* **Facing deadlock or shutdown issues?** Read `events.md` and check `on_close` handler implementations.
```
