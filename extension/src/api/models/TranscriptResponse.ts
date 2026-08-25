/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TranscriptCueResponse } from './TranscriptCueResponse';
export type TranscriptResponse = {
    bvid: string;
    cid: number;
    content_sha256: string;
    created_at: string;
    cues: Array<TranscriptCueResponse>;
    display_name: string;
    kind: string;
    language: string;
    page: number;
    revision_id: string;
    schema_version: number;
    title: string;
    track_id: (string | null);
};

