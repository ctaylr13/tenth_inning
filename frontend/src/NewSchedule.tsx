import ScheduleComponent from "./components/schedule/ScheduleComponent";
export interface Game {
    date: number;
    opponent: string;
    time: string;
    location: string;
}

const NewSchedule = () => {
    return <ScheduleComponent />;
};

export default NewSchedule;
