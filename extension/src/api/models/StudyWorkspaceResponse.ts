/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PersonalNoteResponse } from './PersonalNoteResponse';
import type { ReflectionAttemptResponse } from './ReflectionAttemptResponse';
export type StudyWorkspaceResponse = {
    guide: Record<string, any>;
    notes: Array<PersonalNoteResponse>;
    reflections: Array<ReflectionAttemptResponse>;
    schema_version?: number;
};

