import { styled } from "@linaria/react";

const FIELD_SIZE = 240;
const SCALE = FIELD_SIZE * 0.1;
const DIAMOND_SIZE = FIELD_SIZE * 0.22;

const Field = styled.div`
    width: ${FIELD_SIZE}px;
    aspect-ratio: 1;
    border: 2px solid green;
    background: #e8f5e8;
    position: relative;
`;

const Diamond = styled.div`
    width: ${DIAMOND_SIZE}px;
    aspect-ratio: 1;
    border: 2px solid brown;
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%) rotate(45deg);
`;

const Label = styled.div`
    position: absolute;
    transform: translate(-50%, -50%);
    display: flex;
    flex-direction: column;
    align-items: center;
`;

const PlayerName = styled.div`
    font-size: 12px;
    font-weight: bold;
`;

const PositionText = styled.div`
    font-size: 10px;
`;

interface FieldPositionProps {
    x: number;
    y: number;
    position: string;
    player: string;
}

const FieldPosition = ({ x, y, position, player }: FieldPositionProps) => {
    return (
        <Label
            style={{
                left: `calc(50% + ${x * SCALE}px)`,
                top: `calc(50% - ${y * SCALE}px)`,
            }}
        >
            <PlayerName>{player}</PlayerName>
            <PositionText>{position}</PositionText>
        </Label>
    );
};

const Defense = () => {
    return (
        <Field>
            <Diamond />

            <FieldPosition x={0} y={0} position="P" player="Cole" />
            <FieldPosition x={0} y={-2} position="C" player="Rutschman" />

            <FieldPosition x={-2} y={1} position="3B" player="Devers" />
            <FieldPosition x={-1} y={2} position="SS" player="Bogaerts" />
            <FieldPosition x={1} y={2} position="2B" player="Altuve" />
            <FieldPosition x={2} y={1} position="1B" player="Freeman" />

            <FieldPosition x={-3} y={2.6} position="LF" player="Yelich" />
            <FieldPosition x={0} y={3} position="CF" player="Trout" />
            <FieldPosition x={3} y={2.6} position="RF" player="Judge" />
        </Field>
    );
};

export default Defense;
