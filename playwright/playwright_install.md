# Playwright

[](https://www.youtube.com/watch?v=0lkpbQgfNJk)

## Подготовка окуружения для Playwright

### setup `node.js`

```bash
node -v
```

### setup `VSCode`

#### расширения

- ESLint (VS Code ESLint extension)
- Prettier ESLint (Prettier Formatter for Visual Studio Code)
- Playwright (Playwright Test for VS Code)
- Live Server

VSCode -> Поиск -> (> user settings) -> `settings.json`

##### настройки settings.json

```json
{
  "prettier.tabWidth": 2,
  "prettier.singleQuote": true,
  "prettier.trailingComma": "all",
  "prettier.semi": true,
  "prettier.bracketSameLine": true,
  "prettier.printWidth": 100,
  "editor.formatOnSave": true,
  "[typescript]": {
    "editor.defaultFormatter": "esbenp.prettier-vscode"
  },
  "[json]": {
    "editor.defaultFormatter": "esbenp.prettier-vscode"
  },
  "[javascript]": {
    "editor.defaultFormatter": "esbenp.prettier-vscode"
  },
  "[javascriptreact]": {
    "editor.defaultFormatter": "esbenp.prettier-vscode"
  },
  "editor.codeActionsOnSave": {
    "source.fixAll.eslint": "explicit"
  },
  "files.autoSave": "onFocusChange"
}
```

## Инициализация проекта

```bash
mkdir rlm_playwright
cd rlm_playwright

$ npm init playwright@latest
Need to install the following packages:
create-playwright@1.17.136
Ok to proceed? (y) y


> npx
> create-playwright

Getting started with writing end-to-end tests with Playwright:
Initializing project in '.'
✔ Do you want to use TypeScript or JavaScript? · JavaScript
✔ Where to put your end-to-end tests? · tests
✔ Add a GitHub Actions workflow? (y/N) · false
✔ Install Playwright browsers (can be done manually via 'npx playwright install')? (Y/n) · true
✔ Install Playwright operating system dependencies (requires sudo / root - can be done manually via 'sudo npx playwright install-deps')? (y/N) · false
Initializing NPM project (npm init -y)…
Wrote to /home/alex/Prj/2_dev/AT_lbft/RLM_UItest/rlm_playwright/package.json:

{
  "name": "rlm_playwright",
  "version": "1.0.0",
  "main": "index.js",
  "scripts": {
    "test": "echo \"Error: no test specified\" && exit 1"
  },
  "keywords": [],
  "author": "",
  "license": "ISC",
  "description": ""
}



Installing Playwright Test (npm install --save-dev @playwright/test)…

added 3 packages, and audited 4 packages in 3s

found 0 vulnerabilities
Installing Types (npm install --save-dev @types/node)…

added 2 packages, and audited 6 packages in 2s

found 0 vulnerabilities
Writing playwright.config.js.
Writing tests/example.spec.js.
Writing tests-examples/demo-todo-app.spec.js.
Writing package.json.
Downloading browsers (npx playwright install)…
Downloading Chromium 136.0.7103.25 (playwright build v1169) from https://cdn.playwright.dev/dbazure/download/playwright/builds/chromium/1169/chromium-linux.zip
167.7 MiB [====================] 100% 0.0s
Chromium 136.0.7103.25 (playwright build v1169) downloaded to /home/alex/.cache/ms-playwright/chromium-1169
Downloading Chromium Headless Shell 136.0.7103.25 (playwright build v1169) from https://cdn.playwright.dev/dbazure/download/playwright/builds/chromium/1169/chromium-headless-shell-linux.zip
101.4 MiB [====================] 100% 0.0s
Chromium Headless Shell 136.0.7103.25 (playwright build v1169) downloaded to /home/alex/.cache/ms-playwright/chromium_headless_shell-1169
Downloading Firefox 137.0 (playwright build v1482) from https://cdn.playwright.dev/dbazure/download/playwright/builds/firefox/1482/firefox-ubuntu-24.04.zip
91 MiB [====================] 100% 0.0s
Firefox 137.0 (playwright build v1482) downloaded to /home/alex/.cache/ms-playwright/firefox-1482
Downloading Webkit 18.4 (playwright build v2158) from https://cdn.playwright.dev/dbazure/download/playwright/builds/webkit/2158/webkit-ubuntu-24.04.zip
93.5 MiB [====================] 100% 0.0s
Webkit 18.4 (playwright build v2158) downloaded to /home/alex/.cache/ms-playwright/webkit-2158
Downloading FFMPEG playwright build v1011 from https://cdn.playwright.dev/dbazure/download/playwright/builds/ffmpeg/1011/ffmpeg-linux.zip
2.3 MiB [====================] 100% 0.0s
FFMPEG playwright build v1011 downloaded to /home/alex/.cache/ms-playwright/ffmpeg-1011
Playwright Host validation warning:
╔══════════════════════════════════════════════════════╗
║ Host system is missing dependencies to run browsers. ║
║ Please install them with the following command:      ║
║                                                      ║
║     sudo npx playwright install-deps                 ║
║                                                      ║
║ Alternatively, use apt:                              ║
║     sudo apt-get install libavif16                   ║
║                                                      ║
║ <3 Playwright Team                                   ║
╚══════════════════════════════════════════════════════╝
    at validateDependenciesLinux (/home/alex/Prj/2_dev/AT_lbft/RLM_UItest/rlm_playwright/node_modules/playwright-core/lib/server/registry/dependencies.js:269:9)
    at process.processTicksAndRejections (node:internal/process/task_queues:105:5)
    at async Registry._validateHostRequirements (/home/alex/Prj/2_dev/AT_lbft/RLM_UItest/rlm_playwright/node_modules/playwright-core/lib/server/registry/index.js:927:14)
    at async Registry._validateHostRequirementsForExecutableIfNeeded (/home/alex/Prj/2_dev/AT_lbft/RLM_UItest/rlm_playwright/node_modules/playwright-core/lib/server/registry/index.js:1047:7)
    at async Registry.validateHostRequirementsForExecutablesIfNeeded (/home/alex/Prj/2_dev/AT_lbft/RLM_UItest/rlm_playwright/node_modules/playwright-core/lib/server/registry/index.js:1036:7)
    at async t.<anonymous> (/home/alex/Prj/2_dev/AT_lbft/RLM_UItest/rlm_playwright/node_modules/playwright-core/lib/cli/program.js:160:7)
✔ Success! Created a Playwright Test project at /home/alex/Prj/2_dev/AT_lbft/RLM_UItest/rlm_playwright

Inside that directory, you can run several commands:

  npx playwright test
    Runs the end-to-end tests.

  npx playwright test --ui
    Starts the interactive UI mode.

  npx playwright test --project=chromium
    Runs the tests only on Desktop Chrome.

  npx playwright test example
    Runs the tests in a specific file.

  npx playwright test --debug
    Runs the tests in debug mode.

  npx playwright codegen
    Auto generate tests with Codegen.

We suggest that you begin by typing:

    npx playwright test

And check out the following files:
  - ./tests/example.spec.js - Example end-to-end test
  - ./tests-examples/demo-todo-app.spec.js - Demo Todo App end-to-end tests
  - ./playwright.config.js - Playwright Test configuration

Visit https://playwright.dev/docs/intro for more information. ✨

Happy hacking! 🎭
```

## Пишем первые тесты

## Хуки и группировка тестов

## Аннотации в тестах

## Шаги в тестах

## Параметризация тестов

## Паттер. Page Object Model

## Фикстуры
