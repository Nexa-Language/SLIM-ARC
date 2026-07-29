
// this file is generated — do not edit it


declare module "svelte/elements" {
	export interface HTMLAttributes<T> {
		'data-sveltekit-keepfocus'?: true | '' | 'off' | undefined | null;
		'data-sveltekit-noscroll'?: true | '' | 'off' | undefined | null;
		'data-sveltekit-preload-code'?:
			| true
			| ''
			| 'eager'
			| 'viewport'
			| 'hover'
			| 'tap'
			| 'off'
			| undefined
			| null;
		'data-sveltekit-preload-data'?: true | '' | 'hover' | 'tap' | 'off' | undefined | null;
		'data-sveltekit-reload'?: true | '' | 'off' | undefined | null;
		'data-sveltekit-replacestate'?: true | '' | 'off' | undefined | null;
	}
}

export {};


declare module "$app/types" {
	type MatcherParam<M> = M extends (param : string) => param is (infer U extends string) ? U : string;

	export interface AppTypes {
		RouteId(): "/(chat)" | "/" | "/(chat)/chat" | "/(chat)/chat/[id]" | "/mcp-servers" | "/settings" | "/settings/[[section]]";
		RouteParams(): {
			"/(chat)/chat/[id]": { id: string };
			"/settings/[[section]]": { section?: string }
		};
		LayoutParams(): {
			"/(chat)": { id?: string };
			"/": { id?: string; section?: string };
			"/(chat)/chat": { id?: string };
			"/(chat)/chat/[id]": { id: string };
			"/mcp-servers": Record<string, never>;
			"/settings": { section?: string };
			"/settings/[[section]]": { section?: string }
		};
		Pathname(): "/" | `/chat/${string}` & {} | "/mcp-servers" | `/settings${string}` & {};
		ResolvedPathname(): `${"" | `/${string}`}${ReturnType<AppTypes['Pathname']>}`;
		Asset(): "/apple-splash-landscape-1136x640.png" | "/apple-splash-landscape-1334x750.png" | "/apple-splash-landscape-2266x1488.png" | "/apple-splash-landscape-2360x1640.png" | "/apple-splash-landscape-2388x1668.png" | "/apple-splash-landscape-2532x1170.png" | "/apple-splash-landscape-2556x1179.png" | "/apple-splash-landscape-2622x1206.png" | "/apple-splash-landscape-2732x2048.png" | "/apple-splash-landscape-2778x1284.png" | "/apple-splash-landscape-2796x1290.png" | "/apple-splash-landscape-2868x1320.png" | "/apple-splash-landscape-dark-1136x640.png" | "/apple-splash-landscape-dark-1334x750.png" | "/apple-splash-landscape-dark-2266x1488.png" | "/apple-splash-landscape-dark-2360x1640.png" | "/apple-splash-landscape-dark-2388x1668.png" | "/apple-splash-landscape-dark-2532x1170.png" | "/apple-splash-landscape-dark-2556x1179.png" | "/apple-splash-landscape-dark-2622x1206.png" | "/apple-splash-landscape-dark-2732x2048.png" | "/apple-splash-landscape-dark-2778x1284.png" | "/apple-splash-landscape-dark-2796x1290.png" | "/apple-splash-landscape-dark-2868x1320.png" | "/apple-splash-portrait-1170x2532.png" | "/apple-splash-portrait-1179x2556.png" | "/apple-splash-portrait-1206x2622.png" | "/apple-splash-portrait-1284x2778.png" | "/apple-splash-portrait-1290x2796.png" | "/apple-splash-portrait-1320x2868.png" | "/apple-splash-portrait-1488x2266.png" | "/apple-splash-portrait-1640x2360.png" | "/apple-splash-portrait-1668x2388.png" | "/apple-splash-portrait-2048x2732.png" | "/apple-splash-portrait-640x1136.png" | "/apple-splash-portrait-750x1334.png" | "/apple-splash-portrait-dark-1170x2532.png" | "/apple-splash-portrait-dark-1179x2556.png" | "/apple-splash-portrait-dark-1206x2622.png" | "/apple-splash-portrait-dark-1284x2778.png" | "/apple-splash-portrait-dark-1290x2796.png" | "/apple-splash-portrait-dark-1320x2868.png" | "/apple-splash-portrait-dark-1488x2266.png" | "/apple-splash-portrait-dark-1640x2360.png" | "/apple-splash-portrait-dark-1668x2388.png" | "/apple-splash-portrait-dark-2048x2732.png" | "/apple-splash-portrait-dark-640x1136.png" | "/apple-splash-portrait-dark-750x1334.png" | "/apple-touch-icon-180x180.png" | "/favicon-dark.ico" | "/favicon-dark.svg" | "/favicon.ico" | "/favicon.svg" | "/loading.html" | "/maskable-icon-512x512.png" | "/pwa-192x192.png" | "/pwa-512x512.png" | "/pwa-64x64.png" | string & {};
	}
}