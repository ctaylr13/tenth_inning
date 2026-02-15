import SC_Header from "./SC_Header";
import SC_Main from "./SC_Main";
import SC_Bottom from "./SC_Bottom";
const Scorecard = () => {
    return (
        <div>
            Scorecard
            {/* Top */}
            <SC_Header />
            {/* Middle */}
            <SC_Main />
            {/* Bottom */}
            <SC_Bottom />
        </div>
    );
};

export default Scorecard;
