import Schedule from "./Schedule";
import ScorecardPage from "./components/ScorecardPage";
import NewSchedule from "./NewSchedule";
import LiveGame from "./components/live/LiveGame";
import { lazy, Suspense, useState } from "react";

const PitchTablePage = lazy(
    () => import("./components/pitches/PitchTablePage")
);

const App = () => {
    const [currentAppPage, setCurrentAppPage] = useState("pitches");

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
                <button onClick={() => selectPageOnClick("live")}>live</button>
                <button onClick={() => selectPageOnClick("pitches")}>pitches</button>
            </div>
            {currentAppPage === "schedule" && <Schedule />}
            {currentAppPage === "scorecard" && <ScorecardPage />}
            {currentAppPage === "newSchedule" && <NewSchedule />}
            {currentAppPage === "live" && <LiveGame />}
            {currentAppPage === "pitches" && (
                <Suspense fallback={null}>
                    <PitchTablePage />
                </Suspense>
            )}
        </>
    );
};

export default App;
