// Client half of the API error contract.
export type ErrorCode =
    | "VALIDATION_FAILED"
    | "ROUTE_NOT_FOUND"
    | "RESOURCE_NOT_FOUND"
    | "DUPLICATE_WATCH_ENTRY"
    | "DATA_SOURCE_UNAVAILABLE"
    | "INTERNAL_ERROR";

export type FieldError = { field: string; reason: string };

export type ApiError = {
    code: ErrorCode;
    message: string;
    details: Record<string, unknown>;
    request_id: string;
};

/** Split from Outcome so failure-only state narrows */
export type Failure =
    | { status: "invalid"; fields: FieldError[]; error: ApiError }
    | { status: "conflict"; error: ApiError }
    | { status: "missing"; error: ApiError } // the row, not the route
    | { status: "retry"; error: ApiError } // transient, a retry can succeed
    | { status: "error"; error: ApiError };

export type Outcome<T> = { status: "ok"; data: T } | Failure;

const UNKNOWN: ApiError = {
    code: "INTERNAL_ERROR",
    message: "Something went wrong.",
    details: {},
    request_id: "-",
};

export const request = async <T,>(
    input: RequestInfo,
    init?: RequestInit
): Promise<Outcome<T>> => {
    let res: Response;
    try {
        res = await fetch(input, init);
    } catch {
        // Never landed, so there's no envelope to read
        return {
            status: "retry",
            error: { ...UNKNOWN, code: "DATA_SOURCE_UNAVAILABLE" },
        };
    }

    if (res.ok) return { status: "ok", data: (await res.json()) as T };

    // Fail closed on a shape we didn't define -- something upstream answered
    let error: ApiError;
    try {
        error = ((await res.json()) as { error: ApiError }).error ?? UNKNOWN;
    } catch {
        error = UNKNOWN;
    }

    switch (error.code) {
        case "VALIDATION_FAILED":
            return {
                status: "invalid",
                fields: (error.details.fields as FieldError[]) ?? [],
                error,
            };

        case "DUPLICATE_WATCH_ENTRY":
            return { status: "conflict", error };

        case "RESOURCE_NOT_FOUND":
            return { status: "missing", error };

        case "DATA_SOURCE_UNAVAILABLE":
            return { status: "retry", error };

        default:
            return { status: "error", error };
    }
};
