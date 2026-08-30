/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MindMapResponse } from './MindMapResponse';
import type { PersonalNoteResponse } from './PersonalNoteResponse';
import type { QuizAttemptResponse } from './QuizAttemptResponse';
import type { ReflectionAttemptResponse } from './ReflectionAttemptResponse';
import type { StudySummaryResponse } from './StudySummaryResponse';
export type StudyWorkspaceResponse = {
    guide: Record<string, any>;
    mindmaps?: Array<MindMapResponse>;
    notes: Array<PersonalNoteResponse>;
    quiz_attempts?: Array<QuizAttemptResponse>;
    reflections: Array<ReflectionAttemptResponse>;
    schema_version?: number;
    summaries?: Array<StudySummaryResponse>;
};

