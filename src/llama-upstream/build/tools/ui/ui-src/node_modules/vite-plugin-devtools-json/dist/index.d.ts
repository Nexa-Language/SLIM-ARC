import { Plugin } from 'vite';

declare const plugin: (options?: {
    uuid: string;
}) => Plugin;

export { plugin as default };
