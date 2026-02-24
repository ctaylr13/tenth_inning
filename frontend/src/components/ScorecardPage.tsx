import { styled } from "@linaria/react";
import Scorecard from "./Scorecard/Scorecard";
import Pitcher from "./Scorecard/Pitcher";
import Defense from "./Scorecard/Defense";

const ScorecardHeader = styled.div`
    display: flex;
    flex-direction: row;
    justify-content: space-between;
    padding-top: 1rem;
`;

const HeaderSubsection = styled.div`
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
`;

const HeaderRow = styled.div`
    display: flex;
    flex-direction: row;
    gap: 1rem;
`;

const StyledGrid = styled.div`
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 0.5rem;
`;

const BottomRow = styled.div`
    display: flex;
    flex-direction: row;
    padding-top: 1rem;
`;

const ScorecardPage = () => {
    return (
        <div>
            <ScorecardHeader>
                <div>Top</div>
                <div>Logo</div>
                <HeaderSubsection>
                    <div>Visiting Team: Red Sox (1-1)</div>
                    <HeaderRow>
                        <div>Manager: Alex Cora</div>
                        <div>Uniforms: Home White</div>
                    </HeaderRow>
                </HeaderSubsection>
                <StyledGrid>
                    <div>HP Ump: S Scherwater </div>
                    <div>1B Ump: D Merzel</div>
                    <div>2B Ump: J. Baker</div>
                    <div>3B Ump: J. Jean</div>
                </StyledGrid>
                <HeaderSubsection>
                    <div>Keeping Score by:</div>
                    <div>Watching on screen</div>
                </HeaderSubsection>
                <HeaderSubsection>
                    <div>First Pitch</div>
                    <div>7:10</div>
                </HeaderSubsection>
            </ScorecardHeader>
            {/* Middle */}
            <Scorecard />
            {/* Bottom */}
            <BottomRow>
                <Defense />
                <Pitcher />
            </BottomRow>
        </div>
    );
};

export default ScorecardPage;
