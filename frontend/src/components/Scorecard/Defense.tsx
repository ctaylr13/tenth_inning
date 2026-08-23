import { styled } from "@linaria/react";

const Box = styled.div`
    display: flex;
    flex-direction: column;
`;

const Row = styled.div`
    display: flex;
    flex-direction: row;
    gap: 1rem;
`;

const Defense = () => {
    return (
        <Box>
            <Row>
                <div>1.</div>
                <div>Pitcher</div>
            </Row>
            <Row>
                <div>2.</div>
                <div>Catcher</div>
            </Row>
            <Row>
                <div>3.</div>
                <div>First Base</div>
            </Row>
            <Row>
                <div>4.</div>
                <div>Second Base</div>
            </Row>
            <Row>
                <div>5.</div>
                <div>Third Base</div>
            </Row>
            <Row>
                <div>6.</div>
                <div>Shortstop</div>
            </Row>
            <Row>
                <div>7.</div>
                <div>Left Field</div>
            </Row>
            <Row>
                <div>8.</div>
                <div>Center Field</div>
            </Row>
            <Row>
                <div>9.</div>
                <div>Right Field</div>
            </Row>
        </Box>
    );
};

export default Defense;
