/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type TranscriptPrepareRequest = {
    inspect_job_id: string;
    library: string;
    track_display_name: string;
    track_id: string;
    track_kind: TranscriptPrepareRequest.track_kind;
    track_language: string;
};
export namespace TranscriptPrepareRequest {
    export enum track_kind {
        HUMAN = 'human',
        AI = 'ai',
    }
}

