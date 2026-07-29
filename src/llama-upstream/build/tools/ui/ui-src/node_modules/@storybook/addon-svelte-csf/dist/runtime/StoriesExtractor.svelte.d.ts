import type { Component } from 'svelte';
import type { Cmp } from '../types.js';
import { type StoriesRepository } from './contexts/extractor.svelte';
declare const StoriesExtractor: Component<{
    Stories: Component;
    repository: () => StoriesRepository<Cmp>;
}, {}, "">;
export default StoriesExtractor;
