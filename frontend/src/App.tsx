import Schedule from "./Schedule";
import ScorecardPage from "./components/ScorecardPage";
import NewSchedule from "./NewSchedule";
import { useState } from "react";
import AtBat from "./components/Scorecard/AtBat";
import { styled } from "@linaria/react";

const Container = styled.div`
    display: flex;
    flex-direction: column;
    max-height: 100dvh;
`;
const App = () => {
    const [currentAppPage, setCurrentAppPage] = useState("scorecard");

    const selectPageOnClick = (selectedPage: string) => {
        setCurrentAppPage(selectedPage);
    };

    return (
        <Container>
            <div>
                <button onClick={() => selectPageOnClick("schedule")}>
                    watch schedule
                </button>
                <button onClick={() => selectPageOnClick("scorecard")}>
                    scorecard
                </button>
                <button onClick={() => selectPageOnClick("newSchedule")}>
                    updated schedule
                </button>
                <button onClick={() => selectPageOnClick("atBat")}>
                    at bat
                </button>
            </div>
            {currentAppPage === "schedule" && <Schedule />}
            {currentAppPage === "scorecard" && <ScorecardPage />}
            {currentAppPage === "newSchedule" && <NewSchedule />}
            {currentAppPage === "atBat" && <AtBat />}
        </Container>
    );
};

export default App;
