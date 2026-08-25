/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ChapterDetailRequest } from '../models/ChapterDetailRequest';
import type { ChapterPracticeRequest } from '../models/ChapterPracticeRequest';
import type { JobAccepted } from '../models/JobAccepted';
import type { JobResponse } from '../models/JobResponse';
import type { NoteRequest } from '../models/NoteRequest';
import type { PairRequest } from '../models/PairRequest';
import type { PairResponse } from '../models/PairResponse';
import type { ReflectionRequest } from '../models/ReflectionRequest';
import type { SourceRequest } from '../models/SourceRequest';
import type { VideoInspectRequest } from '../models/VideoInspectRequest';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class DefaultService {
    /**
     *  Health
     * @returns string Successful Response
     * @throws ApiError
     */
    public static health(): CancelablePromise<Record<string, string>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/health',
        });
    }
    /**
     *  Get Job
     * @returns JobResponse Successful Response
     * @throws ApiError
     */
    public static getJob({
        jobId,
    }: {
        jobId: string,
    }): CancelablePromise<JobResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/jobs/{job_id}',
            path: {
                'job_id': jobId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     *  Libraries
     * @returns any Successful Response
     * @throws ApiError
     */
    public static listLibraries(): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/libraries',
        });
    }
    /**
     *  Create Note
     * @returns any Successful Response
     * @throws ApiError
     */
    public static createNote({
        requestBody,
    }: {
        requestBody: NoteRequest,
    }): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/notes',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     *  Pair
     * @returns PairResponse Successful Response
     * @throws ApiError
     */
    public static pair({
        requestBody,
    }: {
        requestBody: PairRequest,
    }): CancelablePromise<PairResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/pair',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     *  Create Reflection
     * @returns JobAccepted Successful Response
     * @throws ApiError
     */
    public static createReflection({
        requestBody,
    }: {
        requestBody: ReflectionRequest,
    }): CancelablePromise<JobAccepted> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/reflections',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     *  List Notes
     * @returns any Successful Response
     * @throws ApiError
     */
    public static listNotes({
        sourceId,
        library,
    }: {
        sourceId: string,
        library: string,
    }): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/sources/{source_id}/notes',
            path: {
                'source_id': sourceId,
            },
            query: {
                'library': library,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     *  Create Study Guide
     * @returns JobAccepted Successful Response
     * @throws ApiError
     */
    public static createStudyGuide({
        requestBody,
    }: {
        requestBody: SourceRequest,
    }): CancelablePromise<JobAccepted> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/study-guides',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     *  Get Study Guide
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getStudyGuide({
        guideId,
        library,
    }: {
        guideId: string,
        library: string,
    }): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/study-guides/{guide_id}',
            path: {
                'guide_id': guideId,
            },
            query: {
                'library': library,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     *  Create Chapter Detail
     * @returns JobAccepted Successful Response
     * @throws ApiError
     */
    public static createChapterDetail({
        guideId,
        chapterId,
        requestBody,
    }: {
        guideId: string,
        chapterId: string,
        requestBody: ChapterDetailRequest,
    }): CancelablePromise<JobAccepted> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/study-guides/{guide_id}/chapters/{chapter_id}/details',
            path: {
                'guide_id': guideId,
                'chapter_id': chapterId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     *  Create Chapter Practice
     * @returns JobAccepted Successful Response
     * @throws ApiError
     */
    public static createChapterPractice({
        guideId,
        chapterId,
        requestBody,
    }: {
        guideId: string,
        chapterId: string,
        requestBody: ChapterPracticeRequest,
    }): CancelablePromise<JobAccepted> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/study-guides/{guide_id}/chapters/{chapter_id}/practice',
            path: {
                'guide_id': guideId,
                'chapter_id': chapterId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     *  Inspect Video
     * @returns JobAccepted Successful Response
     * @throws ApiError
     */
    public static inspectVideo({
        requestBody,
    }: {
        requestBody: VideoInspectRequest,
    }): CancelablePromise<JobAccepted> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/videos/inspect',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     *  Get Video Workspace
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getVideoWorkspace({
        bvid,
        page,
        library,
    }: {
        bvid: string,
        page: number,
        library: string,
    }): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/videos/{bvid}/pages/{page}/workspace',
            path: {
                'bvid': bvid,
                'page': page,
            },
            query: {
                'library': library,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
