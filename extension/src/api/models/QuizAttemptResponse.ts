/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type QuizAttemptResponse = {
    attempt_id: string;
    feedback?: (Record<string, any> | null);
    guide_id: string;
    question_id: string;
    response: string;
    revision_id: string;
    status: QuizAttemptResponse.status;
    submitted_at: string;
};
export namespace QuizAttemptResponse {
    export enum status {
        PENDING = 'pending',
        SUCCEEDED = 'succeeded',
        FEEDBACK_FAILED = 'feedback_failed',
    }
}

