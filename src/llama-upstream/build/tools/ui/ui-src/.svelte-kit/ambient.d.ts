
// this file is generated — do not edit it


/// <reference types="@sveltejs/kit" />

/**
 * This module provides access to environment variables that are injected _statically_ into your bundle at build time and are limited to _private_ access.
 * 
 * |         | Runtime                                                                    | Build time                                                               |
 * | ------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
 * | Private | [`$env/dynamic/private`](https://svelte.dev/docs/kit/$env-dynamic-private) | [`$env/static/private`](https://svelte.dev/docs/kit/$env-static-private) |
 * | Public  | [`$env/dynamic/public`](https://svelte.dev/docs/kit/$env-dynamic-public)   | [`$env/static/public`](https://svelte.dev/docs/kit/$env-static-public)   |
 * 
 * Static environment variables are [loaded by Vite](https://vitejs.dev/guide/env-and-mode.html#env-files) from `.env` files and `process.env` at build time and then statically injected into your bundle at build time, enabling optimisations like dead code elimination.
 * 
 * **_Private_ access:**
 * 
 * - This module cannot be imported into client-side code
 * - This module only includes variables that _do not_ begin with [`config.kit.env.publicPrefix`](https://svelte.dev/docs/kit/configuration#env) _and do_ start with [`config.kit.env.privatePrefix`](https://svelte.dev/docs/kit/configuration#env) (if configured)
 * 
 * For example, given the following build time environment:
 * 
 * ```env
 * ENVIRONMENT=production
 * PUBLIC_BASE_URL=http://site.com
 * ```
 * 
 * With the default `publicPrefix` and `privatePrefix`:
 * 
 * ```ts
 * import { ENVIRONMENT, PUBLIC_BASE_URL } from '$env/static/private';
 * 
 * console.log(ENVIRONMENT); // => "production"
 * console.log(PUBLIC_BASE_URL); // => throws error during build
 * ```
 * 
 * The above values will be the same _even if_ different values for `ENVIRONMENT` or `PUBLIC_BASE_URL` are set at runtime, as they are statically replaced in your code with their build time values.
 */
declare module '$env/static/private' {
	export const VSCODE_CWD: string;
	export const GITHUB_TOKEN: string;
	export const TAVILY_API_KEY: string;
	export const HTTPS_PROXY: string;
	export const VSCODE_ESM_ENTRYPOINT: string;
	export const VSCODE_NLS_CONFIG: string;
	export const USER: string;
	export const no_proxy: string;
	export const KAGGLE_API_TOKEN: string;
	export const npm_config_user_agent: string;
	export const VSCODE_HANDLES_UNCAUGHT_ERRORS: string;
	export const VSCODE_WSL_EXT_LOCATION: string;
	export const DEBUG: string;
	export const npm_node_execpath: string;
	export const LD_LIBRARY_PATH: string;
	export const SHLVL: string;
	export const npm_config_noproxy: string;
	export const OLDPWD: string;
	export const GIT_CONFIG_COUNT: string;
	export const LESS: string;
	export const HOME: string;
	export const VSCODE_RECONNECTION_GRACE_TIME: string;
	export const NO_PROXY: string;
	export const VSCODE_IPC_HOOK_CLI: string;
	export const RUSTUP_UPDATE_ROOT: string;
	export const npm_package_json: string;
	export const LSCOLORS: string;
	export const ZSH: string;
	export const LITELLM_API_KEY: string;
	export const OPENAI_API_KEY: string;
	export const PAGER: string;
	export const COPILOT_OTEL_FILE_EXPORTER_PATH: string;
	export const npm_config_userconfig: string;
	export const npm_config_local_prefix: string;
	export const MAKEFLAGS: string;
	export const DBUS_SESSION_BUS_ADDRESS: string;
	export const RUSTUP_DIST_SERVER: string;
	export const npm_config_engine_strict: string;
	export const POSTHOG_API_KEY: string;
	export const WSL_DISTRO_NAME: string;
	export const COLOR: string;
	export const npm_config_https_proxy: string;
	export const VSCODE_L10N_BUNDLE_LOCATION: string;
	export const WAYLAND_DISPLAY: string;
	export const APPLICATION_INSIGHTS_NO_STATSBEAT: string;
	export const https_proxy: string;
	export const LOGNAME: string;
	export const PULSE_SERVER: string;
	export const VSCODE_HANDLES_SIGPIPE: string;
	export const http_proxy: string;
	export const _P9K_SSH_TTY: string;
	export const NAME: string;
	export const WSL_INTEROP: string;
	export const _: string;
	export const LLAMA_UI_VERSION: string;
	export const LLAMA_BUILD_NUMBER: string;
	export const npm_config_prefix: string;
	export const npm_config_npm_version: string;
	export const TERM: string;
	export const npm_config_proxy: string;
	export const npm_config_cache: string;
	export const npm_config_ignore_scripts: string;
	export const GIT_CONFIG_VALUE_0: string;
	export const OPENAI_API_BASE: string;
	export const npm_config_node_gyp: string;
	export const PATH: string;
	export const OPENAI_MODEL_NAME: string;
	export const NODE: string;
	export const npm_package_name: string;
	export const XDG_RUNTIME_DIR: string;
	export const MAKELEVEL: string;
	export const DISPLAY: string;
	export const LANG: string;
	export const NoDefaultCurrentDirectoryInExePath: string;
	export const LS_COLORS: string;
	export const npm_lifecycle_script: string;
	export const MXC_BIN_DIR: string;
	export const SHELL: string;
	export const npm_package_version: string;
	export const npm_lifecycle_event: string;
	export const GIT_CONFIG_KEY_0: string;
	export const ELECTRON_RUN_AS_NODE: string;
	export const P9K_SSH: string;
	export const proxy_port: string;
	export const LLAMA_UI_OUT_DIR: string;
	export const npm_config_globalconfig: string;
	export const npm_config_init_module: string;
	export const LC_ALL: string;
	export const PWD: string;
	export const npm_execpath: string;
	export const npm_config_global_prefix: string;
	export const HTTP_PROXY: string;
	export const npm_config_allow_scripts: string;
	export const npm_command: string;
	export const MFLAGS: string;
	export const WSL2_GUI_APPS_ENABLED: string;
	export const HOSTTYPE: string;
	export const FIB_DATASET_PATH: string;
	export const WSLENV: string;
	export const INIT_CWD: string;
	export const EDITOR: string;
	export const NODE_ENV: string;
	export const PW_EXPERIMENTAL_SERVICE_WORKER_NETWORK_EVENTS: string;
}

/**
 * This module provides access to environment variables that are injected _statically_ into your bundle at build time and are _publicly_ accessible.
 * 
 * |         | Runtime                                                                    | Build time                                                               |
 * | ------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
 * | Private | [`$env/dynamic/private`](https://svelte.dev/docs/kit/$env-dynamic-private) | [`$env/static/private`](https://svelte.dev/docs/kit/$env-static-private) |
 * | Public  | [`$env/dynamic/public`](https://svelte.dev/docs/kit/$env-dynamic-public)   | [`$env/static/public`](https://svelte.dev/docs/kit/$env-static-public)   |
 * 
 * Static environment variables are [loaded by Vite](https://vitejs.dev/guide/env-and-mode.html#env-files) from `.env` files and `process.env` at build time and then statically injected into your bundle at build time, enabling optimisations like dead code elimination.
 * 
 * **_Public_ access:**
 * 
 * - This module _can_ be imported into client-side code
 * - **Only** variables that begin with [`config.kit.env.publicPrefix`](https://svelte.dev/docs/kit/configuration#env) (which defaults to `PUBLIC_`) are included
 * 
 * For example, given the following build time environment:
 * 
 * ```env
 * ENVIRONMENT=production
 * PUBLIC_BASE_URL=http://site.com
 * ```
 * 
 * With the default `publicPrefix` and `privatePrefix`:
 * 
 * ```ts
 * import { ENVIRONMENT, PUBLIC_BASE_URL } from '$env/static/public';
 * 
 * console.log(ENVIRONMENT); // => throws error during build
 * console.log(PUBLIC_BASE_URL); // => "http://site.com"
 * ```
 * 
 * The above values will be the same _even if_ different values for `ENVIRONMENT` or `PUBLIC_BASE_URL` are set at runtime, as they are statically replaced in your code with their build time values.
 */
declare module '$env/static/public' {
	
}

/**
 * This module provides access to environment variables set _dynamically_ at runtime and that are limited to _private_ access.
 * 
 * |         | Runtime                                                                    | Build time                                                               |
 * | ------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
 * | Private | [`$env/dynamic/private`](https://svelte.dev/docs/kit/$env-dynamic-private) | [`$env/static/private`](https://svelte.dev/docs/kit/$env-static-private) |
 * | Public  | [`$env/dynamic/public`](https://svelte.dev/docs/kit/$env-dynamic-public)   | [`$env/static/public`](https://svelte.dev/docs/kit/$env-static-public)   |
 * 
 * Dynamic environment variables are defined by the platform you're running on. For example if you're using [`adapter-node`](https://github.com/sveltejs/kit/tree/main/packages/adapter-node) (or running [`vite preview`](https://svelte.dev/docs/kit/cli)), this is equivalent to `process.env`.
 * 
 * **_Private_ access:**
 * 
 * - This module cannot be imported into client-side code
 * - This module includes variables that _do not_ begin with [`config.kit.env.publicPrefix`](https://svelte.dev/docs/kit/configuration#env) _and do_ start with [`config.kit.env.privatePrefix`](https://svelte.dev/docs/kit/configuration#env) (if configured)
 * 
 * > [!NOTE] In `dev`, `$env/dynamic` includes environment variables from `.env`. In `prod`, this behavior will depend on your adapter.
 * 
 * > [!NOTE] To get correct types, environment variables referenced in your code should be declared (for example in an `.env` file), even if they don't have a value until the app is deployed:
 * >
 * > ```env
 * > MY_FEATURE_FLAG=
 * > ```
 * >
 * > You can override `.env` values from the command line like so:
 * >
 * > ```sh
 * > MY_FEATURE_FLAG="enabled" npm run dev
 * > ```
 * 
 * For example, given the following runtime environment:
 * 
 * ```env
 * ENVIRONMENT=production
 * PUBLIC_BASE_URL=http://site.com
 * ```
 * 
 * With the default `publicPrefix` and `privatePrefix`:
 * 
 * ```ts
 * import { env } from '$env/dynamic/private';
 * 
 * console.log(env.ENVIRONMENT); // => "production"
 * console.log(env.PUBLIC_BASE_URL); // => undefined
 * ```
 */
declare module '$env/dynamic/private' {
	export const env: {
		VSCODE_CWD: string;
		GITHUB_TOKEN: string;
		TAVILY_API_KEY: string;
		HTTPS_PROXY: string;
		VSCODE_ESM_ENTRYPOINT: string;
		VSCODE_NLS_CONFIG: string;
		USER: string;
		no_proxy: string;
		KAGGLE_API_TOKEN: string;
		npm_config_user_agent: string;
		VSCODE_HANDLES_UNCAUGHT_ERRORS: string;
		VSCODE_WSL_EXT_LOCATION: string;
		DEBUG: string;
		npm_node_execpath: string;
		LD_LIBRARY_PATH: string;
		SHLVL: string;
		npm_config_noproxy: string;
		OLDPWD: string;
		GIT_CONFIG_COUNT: string;
		LESS: string;
		HOME: string;
		VSCODE_RECONNECTION_GRACE_TIME: string;
		NO_PROXY: string;
		VSCODE_IPC_HOOK_CLI: string;
		RUSTUP_UPDATE_ROOT: string;
		npm_package_json: string;
		LSCOLORS: string;
		ZSH: string;
		LITELLM_API_KEY: string;
		OPENAI_API_KEY: string;
		PAGER: string;
		COPILOT_OTEL_FILE_EXPORTER_PATH: string;
		npm_config_userconfig: string;
		npm_config_local_prefix: string;
		MAKEFLAGS: string;
		DBUS_SESSION_BUS_ADDRESS: string;
		RUSTUP_DIST_SERVER: string;
		npm_config_engine_strict: string;
		POSTHOG_API_KEY: string;
		WSL_DISTRO_NAME: string;
		COLOR: string;
		npm_config_https_proxy: string;
		VSCODE_L10N_BUNDLE_LOCATION: string;
		WAYLAND_DISPLAY: string;
		APPLICATION_INSIGHTS_NO_STATSBEAT: string;
		https_proxy: string;
		LOGNAME: string;
		PULSE_SERVER: string;
		VSCODE_HANDLES_SIGPIPE: string;
		http_proxy: string;
		_P9K_SSH_TTY: string;
		NAME: string;
		WSL_INTEROP: string;
		_: string;
		LLAMA_UI_VERSION: string;
		LLAMA_BUILD_NUMBER: string;
		npm_config_prefix: string;
		npm_config_npm_version: string;
		TERM: string;
		npm_config_proxy: string;
		npm_config_cache: string;
		npm_config_ignore_scripts: string;
		GIT_CONFIG_VALUE_0: string;
		OPENAI_API_BASE: string;
		npm_config_node_gyp: string;
		PATH: string;
		OPENAI_MODEL_NAME: string;
		NODE: string;
		npm_package_name: string;
		XDG_RUNTIME_DIR: string;
		MAKELEVEL: string;
		DISPLAY: string;
		LANG: string;
		NoDefaultCurrentDirectoryInExePath: string;
		LS_COLORS: string;
		npm_lifecycle_script: string;
		MXC_BIN_DIR: string;
		SHELL: string;
		npm_package_version: string;
		npm_lifecycle_event: string;
		GIT_CONFIG_KEY_0: string;
		ELECTRON_RUN_AS_NODE: string;
		P9K_SSH: string;
		proxy_port: string;
		LLAMA_UI_OUT_DIR: string;
		npm_config_globalconfig: string;
		npm_config_init_module: string;
		LC_ALL: string;
		PWD: string;
		npm_execpath: string;
		npm_config_global_prefix: string;
		HTTP_PROXY: string;
		npm_config_allow_scripts: string;
		npm_command: string;
		MFLAGS: string;
		WSL2_GUI_APPS_ENABLED: string;
		HOSTTYPE: string;
		FIB_DATASET_PATH: string;
		WSLENV: string;
		INIT_CWD: string;
		EDITOR: string;
		NODE_ENV: string;
		PW_EXPERIMENTAL_SERVICE_WORKER_NETWORK_EVENTS: string;
		[key: `PUBLIC_${string}`]: undefined;
		[key: `${string}`]: string | undefined;
	}
}

/**
 * This module provides access to environment variables set _dynamically_ at runtime and that are _publicly_ accessible.
 * 
 * |         | Runtime                                                                    | Build time                                                               |
 * | ------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
 * | Private | [`$env/dynamic/private`](https://svelte.dev/docs/kit/$env-dynamic-private) | [`$env/static/private`](https://svelte.dev/docs/kit/$env-static-private) |
 * | Public  | [`$env/dynamic/public`](https://svelte.dev/docs/kit/$env-dynamic-public)   | [`$env/static/public`](https://svelte.dev/docs/kit/$env-static-public)   |
 * 
 * Dynamic environment variables are defined by the platform you're running on. For example if you're using [`adapter-node`](https://github.com/sveltejs/kit/tree/main/packages/adapter-node) (or running [`vite preview`](https://svelte.dev/docs/kit/cli)), this is equivalent to `process.env`.
 * 
 * **_Public_ access:**
 * 
 * - This module _can_ be imported into client-side code
 * - **Only** variables that begin with [`config.kit.env.publicPrefix`](https://svelte.dev/docs/kit/configuration#env) (which defaults to `PUBLIC_`) are included
 * 
 * > [!NOTE] In `dev`, `$env/dynamic` includes environment variables from `.env`. In `prod`, this behavior will depend on your adapter.
 * 
 * > [!NOTE] To get correct types, environment variables referenced in your code should be declared (for example in an `.env` file), even if they don't have a value until the app is deployed:
 * >
 * > ```env
 * > MY_FEATURE_FLAG=
 * > ```
 * >
 * > You can override `.env` values from the command line like so:
 * >
 * > ```sh
 * > MY_FEATURE_FLAG="enabled" npm run dev
 * > ```
 * 
 * For example, given the following runtime environment:
 * 
 * ```env
 * ENVIRONMENT=production
 * PUBLIC_BASE_URL=http://example.com
 * ```
 * 
 * With the default `publicPrefix` and `privatePrefix`:
 * 
 * ```ts
 * import { env } from '$env/dynamic/public';
 * console.log(env.ENVIRONMENT); // => undefined, not public
 * console.log(env.PUBLIC_BASE_URL); // => "http://example.com"
 * ```
 * 
 * ```
 * 
 * ```
 */
declare module '$env/dynamic/public' {
	export const env: {
		[key: `PUBLIC_${string}`]: string | undefined;
	}
}
