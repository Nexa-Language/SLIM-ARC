// @ts-nocheck
import type { PageLoad } from './$types';
import { validateApiKey } from '$lib/utils';

export const load = async ({ fetch }: Parameters<PageLoad>[0]) => {
	await validateApiKey(fetch);
};
