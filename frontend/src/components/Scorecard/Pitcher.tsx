import { styled } from "@linaria/react";

const Box = styled.div`
    display: flex;
    flex-direction: row;
    gap: 1rem;
`;

const Pitcher = () => {
    return (
        <Box>
            <div>
                <div>Pitcher</div>
                <div>John Doe</div>
            </div>
            <div>
                <div>R/L</div>
                <div>R</div>
            </div>
            <div>
                <div>IP</div>
                <div>6.2</div>
            </div>
            <div>
                <div>P</div>
                <div>95</div>
            </div>
            <div>
                <div>BF</div>
                <div>27</div>
            </div>
            <div>
                <div>H</div>
                <div>5</div>
            </div>
            <div>
                <div>R</div>
                <div>2</div>
            </div>
            <div>
                <div>ER</div>
                <div>2</div>
            </div>
            <div>
                <div>BB</div>
                <div>1</div>
            </div>
            <div>
                <div>K</div>
                <div>8</div>
            </div>
            <div>
                <div>HR</div>
                <div>1</div>
            </div>
        </Box>
    );
};

export default Pitcher;
