/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type NoteRequest = {
    body: string;
    library: string;
    note_type?: NoteRequest.note_type;
    source_id: string;
    timestamp_ms: number;
};
export namespace NoteRequest {
    export enum note_type {
        NOTE = 'note',
        QUESTION = 'question',
        INSIGHT = 'insight',
    }
}

