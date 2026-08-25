/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { JobProgressResponse } from './JobProgressResponse';
export type JobResponse = {
    created_at: string;
    error_code?: (string | null);
    job_id: string;
    kind: string;
    progress?: (JobProgressResponse | null);
    result?: (Record<string, any> | null);
    retry_of?: (string | null);
    status: JobResponse.status;
    updated_at: string;
};
export namespace JobResponse {
    export enum status {
        QUEUED = 'queued',
        RUNNING = 'running',
        CANCEL_REQUESTED = 'cancel_requested',
        CANCELLED = 'cancelled',
        SUCCEEDED = 'succeeded',
        FAILED = 'failed',
        INTERRUPTED = 'interrupted',
    }
}

