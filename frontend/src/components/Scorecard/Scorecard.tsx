import { styled } from "@linaria/react";

const StyledRow = styled.div`
    display: flex;
    flex-direction: row;
    gap: 1rem;
    padding-top: 1rem;
`;
const Scorecard = () => {
    return (
        <div>
            <StyledRow>
                <div>Player</div>
                <div>Pos.</div>
                <div>1</div>
                <div>2</div>
                <div>3</div>
                <div>4</div>
                <div>5</div>
                <div>6</div>
                <div>7</div>
                <div>8</div>
                <div>9</div>
                <div>10</div>
                <div>11</div>
                <div>AB</div>
                <div>R</div>
                <div>H</div>
                <div>RBI</div>
                <div>SB</div>
            </StyledRow>
            <StyledRow>
                <div>H/R/LOB/SB</div>
                <div>1/2</div>
                <div>1/-/2</div>
                <div>-</div>
                <div>-</div>
                <div>1/2</div>
                <div>1/-/2</div>
                <div>-</div>
                <div>-</div>
                <div>-</div>
                <div>45</div>
                <div>4</div>
                <div>6</div>
                <div>4</div>
                <div>3</div>
            </StyledRow>
        </div>
    );
};

export default Scorecard;
