from datetime import timedelta
import numpy as np
import pandas as pd
from itertools import cycle
import holidays
import time
import json


def truncated_normal(mean, stddev, minval, maxval, size):
    return np.clip(np.random.normal(mean, stddev, size=size), minval, maxval)


def dwell_normal(mean, stddev, minval, maxval, size):
    np.random.seed(12)
    return np.clip(np.random.normal(mean, stddev, size=size), minval, maxval)


def get_n_dates(start, end, n):
    start_u = start.value // (10 ** 9 // 1_000)
    end_u = end.value // (10 ** 9 // 1_000)
    return np.random.randint(start_u, end_u, n, dtype=np.int64)


def hour_weights(h, first_peak, second_peak):
    # We are assuming a sigma (standard deviation from the peak hours) of 2.
    st_time = time.time()
    sigma = 2
    # Gaussian normal distribution with weights for first peak (first_mt) and second peak (second_mt)
    # This simulates the so-called "bell" curve
    hour_weights = 2 * np.exp(-(h - first_peak) ** 2 / (2 * sigma ** 2)) + 1.7 * np.exp(
        -(h - second_peak) ** 2 / (2 * sigma ** 2)) + 0.05
    end_time = time.time()
    # print(h, hour_weights)
    return hour_weights


def dwell_time(event_ts, crowd, overall_mean, overall_sd, first_peak, second_peak):
    # Increase weights compared to timestamp approach to allow for higher mean
    st_time = time.time()
    # Hour
    hour = event_ts.hour
    # Exponential function
    h_wghts = hour_weights(hour, first_peak, second_peak) + 0.5
    # Crowdedness
    crowdedness_wght = 1 + np.log10(crowd + 1) / 5
    #print(np.max(crowdedness_wght))
    # Weights
    wghts = h_wghts * crowdedness_wght
    # dwell times and
    # Stats in ms
    mean = overall_mean * 3_600_000 * wghts
    sd = overall_sd * 3_600_000 * wghts
    end_time = time.time()
    return mean, sd


def normal_dist(hours, mean, sd, min, max, first_peak, second_peak, use_case, anom_weights,
                seasonal_factors, we_holiday_factor):
    # np.random.seed(12)
    st_time = time.time()
    weights = hour_weights(hours, first_peak, second_peak) * anom_weights * seasonal_factors * we_holiday_factor
    # More variance for low footfall times, less for high footfall times
    # The higher the footfall (weights) the more people are queueing, hence, we multiply
    if use_case != "freeSeats":
        weighted_mean, weighted_sd = mean * weights, sd * np.sqrt(weights)
    else:
        # The higher the footfall the lower the availability of free seats, hence, we divide
        weighted_mean, weighted_sd = mean / weights, sd * np.sqrt(weights)

    if use_case == "event":
        end_time = time.time()
        return weighted_mean, weighted_sd

    else:
        weighted_mean = np.asarray(weighted_mean)
        weighted_sd = np.asarray(weighted_sd)
        weighted_mean[weighted_mean > max] = max
        weighted_sd[weighted_sd < 1] = 1
        traffic_arr = truncated_normal(weighted_mean, weighted_sd, min, max, len(hours))
        end_time = time.time()
        return traffic_arr


def anomaly_weights(float_h):
    # We are assuming a sigma (standard deviation from the peak hours) of 2.
    # Convert to ms
    st_time = time.time()
    sigma = 2 * 3_600_000

    # Difference between two timestamps is 10 seconds (10_000 ms)
    seq_start = 0
    len_seq = len(float_h)
    seq = np.arange(seq_start, seq_start + (10_000 * len_seq), 10_000)

    # Anomaly peak pre-defined at center of time-series array
    arr_peak = len(seq) // 2

    # Peak
    mu = seq[arr_peak]
    mu_h = float_h[arr_peak]
    if mu_h < 5 or mu_h > 19:
        factor = np.random.uniform(10, 20)
    else:
        factor = np.random.uniform(2, 4)

    # If weight below 0, then bring it back to 1 by dividing
    weights = np.exp(-(seq - mu) ** 2 / (2 * sigma ** 2)) * factor

    end_time = time.time()
    return weights


# Generate n random dates within time range
def random_dates(start, end, n, freq, unit):
    st_time = time.time()
    np.random.seed(12)
    dr_lst = []
    days = (end - start).days
    arr = start + pd.to_timedelta(np.random.randint(0, days * 24, n), unit=unit)
    sorted_arr = arr.sort_values()
    len_arr = len(sorted_arr)
    # get start date of anomaly
    start_dt = cycle(sorted_arr)
    next_dt = next(start_dt)
    step = 0
    while step < len_arr:
        step += 1
        if step < n:
            current_dt, next_dt = next_dt, next(start_dt)
        else:
            current_dt, next_dt = next_dt, end
        # print(freq)
        dr = create_date_range(current_dt, next_dt, freq)
        dr_lst.append(dr)

    end_time = time.time()
    return dr_lst


# Generate range from random date
def create_date_range(start_dt, next_dt, freq):
    st_time = time.time()
    seconds = int(freq[:-1])
    duration = float(truncated_normal(10, 3, 1, 20, 1))
    end_dt = min(start_dt + timedelta(hours=duration), next_dt - timedelta(seconds=seconds))
    dr = pd.date_range(start=start_dt, end=end_dt, freq=freq)
    end_time = time.time()
    return dr


# Generate mean and std in case there is an anomaly in footfall going on.
# Generates an array for timestamp, and tuple (mean, std) for event data.


def random_anomaly_generator(dr, start, end, n, freq, unit="H"):
    st_time = time.time()
    # Regel das mit random seed 10
    start = pd.to_datetime(start)
    end = pd.to_datetime(end)
    ts = random_dates(start, end, n, freq, unit)
    # Weights and normal dist
    weights_h = anom_weight_arr(ts, dr)
    anom_weights = np.clip(weights_h, 1, 50)
    end_time = time.time()
    return anom_weights


def anomaly_weights_event(start, peak, event_dt):
    # We are assuming a sigma (standard deviation from the peak hours) of 2.
    # Convert to ms
    st_time = time.time()
    sigma = 2 * 3_600_000
    # Peak
    peak_h = peak.hour + (peak.minute / 60) + (peak.second / 60 / 60)
    # Start - Peak difference
    # Time starts at 0 ms
    # peak ms
    peak_ms = (peak - start).total_seconds() * 1_000

    # Event date time
    #  print(event_dt)
    event_ms = (event_dt - start).total_seconds() * 1_000

    if peak_h < 5 or peak_h > 19:
        factor = np.random.uniform(10, 20)
    else:
        factor = np.random.uniform(2, 4)

    # If weight below 0, then bring it back to 1 by dividing
    weight = np.exp(-(event_ms - peak_ms) ** 2 / (2 * sigma ** 2)) * factor
    end_time = time.time()
    return weight


def anom_weight_arr(anom_dt, dt):
    # Returns np array indicating whether index is an anomaly
    # Concat list to one array and use as mask for whole range
    weight_arr = np.ones(len(dt))
    for anom_seq in anom_dt:
        # print(anom_seq)
        start = anom_seq[0]
        end = anom_seq[-1]
        peak = start + (end - start) / 2
        in_seq = dt.isin(anom_seq)
        selected_anoms = dt[in_seq]
        anom_weights = anomaly_weights_event(start, peak, selected_anoms)
        # Returns True for anomalies that are NOT in the current sequence, False otherwise
        not_in_seq = ~dt.isin(anom_seq)
        # Turn to int
        weight_mask = not_in_seq.astype(float)
        weight_mask[weight_mask < 1] = anom_weights
        weight_arr *= weight_mask
    return weight_arr


def get_month_diff(prev_year, current_year, next_year, current_month, month_peak):
    # Peak of last year
    prev_year_diff = (current_year - prev_year) * 12 + (current_month - month_peak)
    # Peak of this year
    this_year_diff = current_month - month_peak
    # Peal of next year
    next_year_diff = (current_year - next_year) * 12 + (current_month - month_peak)

    return np.minimum.reduce([np.absolute(prev_year_diff),
                              np.absolute(this_year_diff),
                              np.absolute(next_year_diff)])


def seasonality_factor(first_peak, second_peak, current_month, current_year):
    # In months
    sigma = 2
    next_year = current_year + 1
    prev_year = current_year - 1
    # To depict correct month difference in case events are in different years
    month_diff_1 = get_month_diff(prev_year, current_year, next_year, current_month, first_peak)
    month_diff_2 = get_month_diff(prev_year, current_year, next_year, current_month, second_peak)
    factor = 0.65 * np.exp(-(month_diff_1) ** 2 / (2 * sigma ** 2)) + \
             0.45 * np.exp(-(month_diff_2) ** 2 / (2 * sigma ** 2)) + 0.7
    return factor


def holidays_in_uk(start_ts, end_ts):
    start, end = pd.to_datetime(start_ts), pd.to_datetime(end_ts)
    n_dates = end - start
    uk_holidays = holidays.England()
    holiday_lst = [(start + timedelta(days=day)).date() for day in range(n_dates.days + 1) if
                   (start + timedelta(days=day)) in uk_holidays]
    return holiday_lst


def greedy_split(arr, n, axis=0):
    """Greedily splits an array into n blocks.

    Splits array arr along axis into n blocks such that:
        - blocks 1 through n-1 are all the same size
        - the sum of all block sizes is equal to arr.shape[axis]
        - the last block is nonempty, and not bigger than the other blocks

    Intuitively, this "greedily" splits the array along the axis by making
    the first blocks as big as possible, then putting the leftovers in the
    last block.
    """
    length = arr.shape[axis]

    # compute the size of each of the first n-1 blocks
    block_size = np.ceil(length / float(n))

    # the indices at which the splits will occur
    ix = np.arange(block_size, length, block_size).astype(int)

    return np.split(arr, ix, axis)


def weekend_holiday_factor(dt, holidays, higher_weekdays):
    dt = np.array(dt, dtype="datetime64[D]")
    # print(len(dt))
    is_busday = np.is_busday(dt, holidays=holidays)
    holiday_dt = dt[is_busday == False]
    n_holidays = len(np.unique(holiday_dt))
    hol_arr = greedy_split(holiday_dt, n_holidays)
    # Initialise weight array
    weight_arr = np.ones(len(dt))
    # Assign random value per date in array
    for i in range(len(hol_arr)):
        day_seq = hol_arr[i]
        mask = np.isin(dt, day_seq[0])
        # If venue has higher footfall on weekdays, then the factor for weekends should be
        # below 1.
        if higher_weekdays:
            random_weight = truncated_normal(0.75, 0.05, 0.5, 0.8, size=1)
        else:
            random_weight = truncated_normal(1.25, 0.05, 1.1, 1.5, size=1)
        day_factor = np.where(mask, random_weight, 1)
        weight_arr *= day_factor
    # Make customisable when introducing inputs to program
    we_hol_factor = np.where(is_busday, 1, weight_arr)
    return we_hol_factor


def weekends(start, end):
    df = pd.DataFrame({'Dates': pd.date_range(start, end)})
    busines_dates = pd.bdate_range(start, end)
    answer = df.loc[~df['Dates'].isin(busines_dates)]
    weekends = answer["Dates"].astype(str)
    return weekends.tolist()


# DATABASE UTILS
class CustomEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        else:
            return super(CustomEncoder, self).default(obj)


def preprocess_for_mongo(data):
    for rec in data:
        if "timestamp" in rec:
            rec["timestamp"] = rec["timestamp"].to_pydatetime().isoformat()
    data_dict = json.dumps(data, cls=CustomEncoder)
    data = json.loads(data_dict)

    return data


def retrieve_from_mongo(collection, db):
    if collection != db["scenario"]:
        data = collection.find()
        df = pd.DataFrame.from_records(data)
        df = df.drop(columns="_id")
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    else:
        df = collection.find()
    return df


def yes_no(question):
    """
    Function for user to answer a yes/no question.


    Parameters:
        (str) question: A question which provides context on why the yes/no question is asked.

    Returns:
        (str) choice: the choice of the user, either 'y' or 'n'
    """
    # Outputs 'y' or 'n' as a string, or prompts the user for another choice
    while True:
        choice = str(input(
            f"{str(question)} Yes or No? Please type y for yes, n for No: ").strip().lower())
        acceptable_inputs = ['yes', 'no', 'nah',
                             'yeh', 'nope', 'yeah', 'y', 'n']
        if choice in acceptable_inputs:
            choice = choice[:1]
            return choice
        else:
            print(f'{choice} is an invalid input! Please enter either y or n')
            continue


def exception_handler_id(user_input: str, dataframe):
    """
    Function to handle user input, when user needs to input an integer found in the index of the data frame

    Parameters:
        (str) user_input
        (df) dataframe

    Returns:
        (int) Integer of user input, if in data frame index
        (str) A string saying the input is "Invalid", if user input not in data frame
    """
    try:
        if int(user_input) not in dataframe.index:
            raise ValueError
        return int(user_input)
    except ValueError:
        retry = yes_no("\nYou did not enter a valid number. You must select a number that appears in the list, "
                       "would you like to try again?")
        if retry == 'y':
            new_input = input(
                "\nPlease select one number from the left hand side of the overview: ")
            return exception_handler_id(new_input, dataframe)
        else:
            return "Invalid"


# Insert new data set to mongodb
def insert_to_mongodb(total_df, collection, db, update=None):
    data = preprocess_for_mongo(total_df)
    if not update:
        collection.delete_many({})
    collection.insert_many(data)
    if collection != db["scenario"] and collection != db["devices"]:
        collection.update_many({}, [{'$set': {'timestamp': {'$toDate': '$timestamp'}}}])
    return True


def cum_visitor_count(collection):
    collection.aggregate([
        {
            '$match': {
                'recordType': '3'
            }
        }, {
            '$addFields': {
                'value': {
                    '$cond': {
                        'if': {
                            '$eq': [
                                '$event', 'personIn'
                            ]
                        },
                        'then': 1,
                        'else': -1
                    }
                }
            }
        }, {
            '$group': {
                '_id': {
                    'time': {
                        '$toDate': {
                            '$dateToString': {
                                'format': '%Y-%m-%d %H:00:00',
                                'date': '$timestamp',
                            }
                        }
                    }},
                'value': {
                    '$sum': '$value'
                }
            }
        }, {
            '$addFields': {
                '_id': '$_id.time'
            }
        }, {
            '$sort': {
                '_id': 1
            }
        }, {
            '$group': {
                '_id': None,
                'data': {
                    '$push': '$$ROOT'
                }
            }
        }, {
            '$addFields': {
                'data': {
                    '$reduce': {
                        'input': '$data',
                        'initialValue': {
                            'total': 0,
                            'd': []
                        },
                        'in': {
                            'total': {
                                '$sum': [
                                    '$$this.value', '$$value.total'
                                ]
                            },
                            'd': {
                                '$concatArrays': [
                                    '$$value.d', [
                                        {
                                            '_id': '$$this._id',
                                            'value': '$$this.value',
                                            'runningTotal': {
                                                '$sum': [
                                                    '$$value.total', '$$this.value'
                                                ]
                                            }
                                        }
                                    ]
                                ]
                            }
                        }
                    }
                }
            }
        }, {
            '$unwind': '$data.d'
        }, {
            '$replaceRoot': {
                'newRoot': '$data.d'
            }
        }, {
            '$out': 'cumVisitorCount'
        }
    ])
    return True
