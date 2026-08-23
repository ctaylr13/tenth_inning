import React from "react";
import { styled } from "@linaria/react";

import type { Failure } from "../../api/errors";

type ScheduleFailureProps = {
    failure: Failure;
    onRetry: () => void;
};

const Panel = styled.div`
    padding: 1rem;
`;

const RequestId = styled.p`
    color: #666;
    font-family: monospace;
`;

const ScheduleFailure: React.FC<ScheduleFailureProps> = ({
    failure,
    onRetry,
}) => (
    <Panel>
        <p>{failure.error.message}</p>
        {/* A retry can succeed on its own, so the id would just be noise */}
        {failure.status !== "retry" && (
            <RequestId>request id: {failure.error.request_id}</RequestId>
        )}
        <button onClick={onRetry}>Try again</button>
    </Panel>
);

export default ScheduleFailure;
