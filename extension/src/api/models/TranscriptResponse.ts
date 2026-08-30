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
    inspection_job_id: (string | null);
    kind: string;
    language: string;
    page: number;
    page_identity_source: string;
    revision_id: string;
    schema_version: number;
    source_verification: TranscriptResponse.source_verification;
    title: string;
    track_id: (string | null);
};
export namespace TranscriptResponse {
    export enum source_verification {
        VERIFIED = 'verified',
        LEGACY_UNVERIFIED = 'legacy_unverified',
    }
}

