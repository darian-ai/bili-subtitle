/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { StoredGuideSummary } from './StoredGuideSummary';
export type VideoWorkspaceLookup = {
    bvid: string;
    guide_id: (string | null);
    guide_versions?: Array<StoredGuideSummary>;
    page: number;
    revision_id: (string | null);
    schema_version?: number;
};

