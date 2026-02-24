import Schedule from "./Schedule";
import ScorecardPage from "./components/ScorecardPage";
import { useState } from "react";

const App = () => {
    const [currentAppPage, setCurrentAppPage] = useState("scorecard");

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
            </div>
            {currentAppPage === "schedule" ? <Schedule /> : <ScorecardPage />}
        </>
    );
};

export default App;
