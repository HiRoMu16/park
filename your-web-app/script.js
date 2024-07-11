function calculateDay() {
    const dateInput = document.getElementById('dateInput').value;
    if (dateInput) {
        const date = new Date(dateInput);
        const weekdays = ["日", "月", "火", "水", "木", "金", "土"];
        const day = date.getDay();
        const resultText = weekdays[day] + "曜日";
        
        document.getElementById('result').textContent = "入力された日付は " + resultText + " です。";
    } else {
        document.getElementById('result').textContent = "有効な日付を入力してください。";
    }
}