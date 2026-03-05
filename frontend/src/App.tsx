import Schedule from "./Schedule";
import ScorecardPage from "./components/ScorecardPage";
import NewSchedule from "./NewSchedule";
import { useState } from "react";

const App = () => {
    const [currentAppPage, setCurrentAppPage] = useState("newSchedule");

    const selectPageOnClick = (selectedPage: string) => {
        setCurrentAppPage(selectedPage);
    };

    return (
        <>
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
            </div>
            {currentAppPage === "schedule" && <Schedule />}
            {currentAppPage === "scorecard" && <ScorecardPage />}
            {currentAppPage === "newSchedule" && <NewSchedule />}
        </>
    );
};

export default App;
