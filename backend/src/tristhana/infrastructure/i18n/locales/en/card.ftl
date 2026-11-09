# ST-07 share cards (ADR-0040). Public text: strangers read it, so it never addresses the
# reader ("you", "your") and states facts only. No emoji: the cards draw their own marks.
card-footer = Tristhana · @tristhana_bot
card-month-practices =
    { $count ->
        [one] { $count } practice day in { $month ->
            [1] January
            [2] February
            [3] March
            [4] April
            [5] May
            [6] June
            [7] July
            [8] August
            [9] September
            [10] October
            [11] November
           *[12] December
        }
       *[other] { $count } practice days in { $month ->
            [1] January
            [2] February
            [3] March
            [4] April
            [5] May
            [6] June
            [7] July
            [8] August
            [9] September
            [10] October
            [11] November
           *[12] December
        }
    }
card-month-time =
    { $hours ->
        [0] { $minutes } min on the mat
       *[other] { $minutes ->
            [0] { $hours } h on the mat
           *[other] { $hours } h { $minutes } min on the mat
        }
    }
card-series-name =
    { $n ->
        [1] Primary series
        [2] Intermediate series
        [3] Advanced A (third series)
        [4] Advanced B (fourth series)
        [5] Advanced C (fifth series)
       *[6] Advanced D (sixth series)
    }
card-year-so-far =
    { $count ->
        [one] { $year } so far: { $count } practice
       *[other] { $year } so far: { $count } practices
    }
card-year-done =
    { $count ->
        [one] { $count } practice in { $year }
       *[other] { $count } practices in { $year }
    }
card-legend-practice = practice
card-legend-moon = moon day
card-new-asana = New asana
card-series-begins =
    { $n ->
        [1] Primary series begins
        [2] Intermediate series begins
        [3] Advanced A begins
        [4] Advanced B begins
        [5] Advanced C begins
       *[6] Advanced D begins
    }
card-series-complete =
    { $n ->
        [1] Full Primary series
        [2] Full Intermediate series
        [3] Full Advanced A
        [4] Full Advanced B
        [5] Full Advanced C
       *[6] Full Advanced D
    }
card-count =
    { $count ->
        [one] practice on the mat
       *[other] practices on the mat
    }
card-series-other-name =
    { $n ->
        [3] Third series
        [4] Fourth series
        [5] Fifth series
       *[6] Sixth series
    }
