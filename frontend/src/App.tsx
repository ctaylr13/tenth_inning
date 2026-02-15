import Schedule from "./Schedule";
import Scorecard from "./components/Scorecard";
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
                    schedule
                </button>
                <button onClick={() => selectPageOnClick("scorecard")}>
                    scorecard
                </button>
            </div>
            {currentAppPage === "schedule" ? <Schedule /> : <Scorecard />}
        </>
    );
};

export default App;
