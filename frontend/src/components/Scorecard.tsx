import { styled } from "@linaria/react";

const Box = styled.div`
    display: flex;
    flex-direction: row;
`;
const Scorecard = () => {
    return (
        <div>
            Scorecard
            {/* Top */}
            <Box>
                <div>Team Logo</div>
                <div>Visiting Team</div>
                <div>Manager</div>
                <div>Uniforms</div>
                <div>Umpires</div>
                <div>Keeping Score by</div>
                <div>First Pitch</div>
            </Box>
            {/* Middle */}
            <div>Middle</div>
            {/* Bottom */}
            <div>Bottom</div>
        </div>
    );
};

export default Scorecard;
