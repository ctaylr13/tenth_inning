import MonthComponent from "./components/schedule/MonthComponent";
export interface Game {
    date: number;
    opponent: string;
    time: string;
    location: "home" | "away";
}

const marchGames: Game[] = [
    { date: 1, opponent: "TEX", time: "7:10", location: "home" },
    { date: 2, opponent: "TEX", time: "7:10", location: "home" },
    { date: 3, opponent: "TEX", time: "1:10", location: "away" },
    { date: 4, opponent: "NYY", time: "7:05", location: "away" },
    { date: 5, opponent: "NYY", time: "7:05", location: "away" },
    { date: 6, opponent: "BAL", time: "6:35", location: "home" },
    { date: 7, opponent: "BAL", time: "6:35", location: "home" },
    { date: 8, opponent: "BAL", time: "1:35", location: "home" },
    { date: 10, opponent: "TB", time: "7:10", location: "away" },
    { date: 11, opponent: "TB", time: "7:10", location: "away" },
    { date: 12, opponent: "TB", time: "1:10", location: "away" },
    { date: 14, opponent: "SEA", time: "7:10", location: "home" },
    { date: 15, opponent: "SEA", time: "7:10", location: "home" },
    { date: 16, opponent: "SEA", time: "1:10", location: "home" },
    { date: 18, opponent: "TOR", time: "7:07", location: "away" },
    { date: 19, opponent: "TOR", time: "7:07", location: "away" },
    { date: 21, opponent: "KC", time: "7:10", location: "home" },
    { date: 23, opponent: "KC", time: "1:10", location: "home" },
    { date: 26, opponent: "LAD", time: "10:10", location: "away" },
    { date: 30, opponent: "MIN", time: "7:10", location: "home" },
];

const NewSchedule = () => {
    return (
        <div>
            <MonthComponent
                title="March / April"
                games={marchGames}
                daysInMonth={31}
            />
        </div>
    );
};

export default NewSchedule;
