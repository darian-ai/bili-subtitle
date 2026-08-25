/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type VideoInspectRequest = {
    bvid: string;
    collection_index?: (number | null);
    collection_total?: (number | null);
    identity_evidence?: VideoInspectRequest.identity_evidence;
    identity_state?: string;
    library: string;
    page: number;
};
export namespace VideoInspectRequest {
    export enum identity_evidence {
        URL_PAGE = 'url_page',
        VIDEO_POD_PAGE = 'video_pod_page',
        VIDEO_POD_ITEM = 'video_pod_item',
        SINGLE_VIDEO = 'single_video',
    }
}

