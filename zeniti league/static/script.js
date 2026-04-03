// მიუთითეთ შემდეგი თამაშის თარიღი და დრო
const nextMatchDate = new Date("July 15, 2026 18:00:00").getTime();

const timerFunction = setInterval(function() {
    const now = new Date().getTime();
    const distance = nextMatchDate - now;

    // დროის გამოთვლა დღეებში, საათებში, წუთებსა და წამებში
    const days = Math.floor(distance / (1000 * 60 * 60 * 24));
    const hours = Math.floor((distance % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    const minutes = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60));
    const seconds = Math.floor((distance % (1000 * 60)) / 1000);

    // შედეგების გამოტანა შესაბამის ID-ებში
    document.getElementById("days").innerHTML = days;
    document.getElementById("hours").innerHTML = hours;
    document.getElementById("minutes").innerHTML = minutes;
    document.getElementById("seconds").innerHTML = seconds;

    // თუ დრო ამოიწურა
    if (distance < 0) {
        clearInterval(timerFunction);
        document.getElementById("countdown-container").innerHTML = "<h3>თამაში დაწყებულია! ⚽</h3>";
    }
}, 1000);