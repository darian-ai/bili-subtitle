/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type SourceRequest = {
    bvid: string;
    cid: number;
    library: string;
    page: number;
    provider: string;
    regenerate?: boolean;
    title: string;
    track_display_name?: (string | null);
    track_id: string;
    track_kind?: ('human' | 'ai' | null);
    track_language?: (string | null);
};

