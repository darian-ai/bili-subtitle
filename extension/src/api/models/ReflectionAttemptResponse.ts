/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ReflectionAttemptResponse = {
    feedback?: (Record<string, any> | null);
    guide_id: string;
    question_id: string;
    reflection_id: string;
    response: string;
    status: ReflectionAttemptResponse.status;
    submitted_at?: (string | null);
};
export namespace ReflectionAttemptResponse {
    export enum status {
        PENDING = 'pending',
        SUCCEEDED = 'succeeded',
        FEEDBACK_FAILED = 'feedback_failed',
    }
}

