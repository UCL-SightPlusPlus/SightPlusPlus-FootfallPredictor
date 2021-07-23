from datetime import timedelta
import numpy as np
import datetime
from datetime import date
import pandas as pd
from itertools import cycle
import holidays


# Convert datetime object to milliseconds
def convert_to_ms(dt):
    # Start of utc epoch
    epoch = datetime.datetime.utcfromtimestamp(0)
    ms = (dt - epoch).total_seconds() * 1000
    return int(ms)


def convert_arr_to_ms(dt):
    # Start of utc epoch
    epoch = datetime.datetime.utcfromtimestamp(0)
    ms = (dt - epoch).total_seconds() * 1000
    return ms.astype(int)


def truncated_normal(mean, stddev, minval, maxval, size):
    return np.clip(np.random.normal(mean, stddev, size=size), minval, maxval)


def ms_weights(ts):
    # We are assuming a sigma (standard deviation from the peak hours) of 2.
    # Convert to ms
    sigma = 2 * 3_600_000

    float_h = 3_600_000 * (ts.hour + (ts.minute / 60) + (ts.second / 60 / 60))
    start = float_h[0]
    end = float_h[-1]
    # Peak
    mu = (start + end) / 2
    ms_weights = np.exp(-(float_h - mu) ** 2 / (2 * sigma ** 2))

    return ms_weights


def hour_weights(h, first_peak, second_peak):
    # We are assuming a sigma (standard deviation from the peak hours) of 2.
    sigma = 2
    # Gaussian normal distribution with weights for first peak (first_mt) and second peak (second_mt)
    # This simulates the so-called "bell" curve
    hour_weights = 2 * np.exp(-(h - first_peak) ** 2 / (2 * sigma ** 2)) + 1.7 * np.exp(
        -(h - second_peak) ** 2 / (2 * sigma ** 2)) + 0.05

    return hour_weights


def dwell_time(hour, overall_mean, overall_sd, first_peak, second_peak):
    # Increase weights compared to timestamp approach to allow for higher mean
    wghts = hour_weights(hour, first_peak, second_peak) + 0.5
    # dwell times and
    # Stats in ms
    mean = overall_mean * 3_600_000 * wghts
    sd = overall_sd * 3_600_000 * wghts

    return mean, sd


def normal_dist(hours, mean, sd, min, max, first_peak, second_peak, use_case, anom_weights, seasonal_factors,
                weekend_holiday_factors):
    # np.random.seed(12)
    weights = hour_weights(hours, first_peak, second_peak) * anom_weights * seasonal_factors * weekend_holiday_factors
    # More variance for low footfall times, less for high footfall times
    # The higher the footfall (weights) the more people are queueing, hence, we multiply
    if use_case != "freeSeats":
        weighted_mean, weighted_sd = mean * weights, sd * np.sqrt(weights)
    else:
        # The higher the footfall the lower the availability of free seats, hence, we divide
        weighted_mean, weighted_sd = mean / weights, sd * np.sqrt(weights)

    if use_case == "event":
        return weighted_mean, weighted_sd

    else:
        weighted_mean = np.asarray(weighted_mean)
        weighted_sd = np.asarray(weighted_sd)
        weighted_mean[weighted_mean > max] = max
        weighted_sd[weighted_sd < 1] = 1
        traffic_arr = truncated_normal(weighted_mean, weighted_sd, min, max, len(hours))
        return traffic_arr


def anomaly_weights(float_h):
    # We are assuming a sigma (standard deviation from the peak hours) of 2.
    # Convert to ms
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

    return weights


# Generate n random dates within time range
def random_dates(start, end, n, use_case, unit):
    np.random.seed(12)
    dr_lst = []
    float_ts_lst = []
    days = (end - start).days + 1
    arr = start + pd.to_timedelta(np.random.randint(0, days * 24, n), unit=unit)
    sorted_arr = arr.sort_values()
    len_arr = len(sorted_arr) - 1
    # get start date of anomaly
    start_dt = cycle(sorted_arr)
    next_dt = next(start_dt)
    step = 0
    while step < len_arr:
        step += 1
        current_dt, next_dt = next_dt, next(start_dt)
        dr = create_date_range(use_case, current_dt, next_dt, "10S")
        dr_lst.append(dr)
        if use_case != "event":
            float_h = dr.hour + (dr.minute / 60) + (dr.second / 60 / 60)
            float_m = dr.month + (dr.day / 31) + (float_h / 24 / 31)
            float_ts_lst.append((dr.year, float_m, dr.day, float_h))

    if use_case != "event":
        anom_dt = dr_lst[0].union_many(dr_lst[1:])
        return anom_dt, float_ts_lst

    else:
        return dr_lst


# Generate range from random date
def create_date_range(use_case, start_dt, next_dt, freq):
    duration = float(truncated_normal(10, 3, 1, 20, 1))
    end_dt = min(start_dt + timedelta(hours=duration), next_dt - timedelta(seconds=10))
    if use_case != "event":
        dr = pd.date_range(start=start_dt, end=end_dt, freq=freq)
        return dr
    else:
        return start_dt, end_dt


# Generate mean and std in case there is an anomaly in footfall going on.
# Generates an array for timestamp, and tuple (mean, std) for event data.

def random_anomaly_generator(mean, sd, min, max, first_peak, second_peak, high_seasons, holidays, use_case, start, end,
                             n,
                             unit="H"):
    # Regel das mit random seed 10
    start = pd.to_datetime(start)
    end = pd.to_datetime(end)
    ts = random_dates(start, end, n, use_case, unit)
    if use_case != "event":
        anomaly_lst = []
        anom_dt = ts[0]
        float_ts_lst = ts[1]
        for years, months, days, hours in float_ts_lst:
            # Weights and normal dist
            weights_h = anomaly_weights(hours)
            anom_weights = np.clip(weights_h, 1, 8)
            # Seasonality
            seasonality = seasonality_factor(high_seasons[0], high_seasons[1], months, years)

            # Weekends and holidays
            we_holiday_factor = weekend_holiday_factor(years, months.astype(int), days, holidays)

            anom_result = normal_dist(hours, mean, sd, min, max, first_peak, second_peak, use_case, anom_weights,
                                      we_holiday_factor, seasonality)
            anomaly_lst.append(anom_result)
        anomalies = np.asarray(anomaly_lst)
        anom_arr = np.concatenate(anomalies)

        return anom_dt, anom_arr
    else:
        return ts


def anomaly_weights_event(start, peak, event_dt):
    # We are assuming a sigma (standard deviation from the peak hours) of 2.
    # Convert to ms
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
    return weight


def is_anomaly(anom_dt, current_dt):
    for date in anom_dt:
        start = date[0]
        end = date[1]
        if start <= current_dt <= end:
            peak = start + (end - start) / 2
            return start, peak
        else:
            continue
    return False


def seasonality_factor(first_peak, second_peak, current_month, current_year):
    # In months
    sigma = 2
    # To depict correct month difference in case events are in different years
    month_diff_1 = (current_year - first_peak[0]) * 12 + (current_month - first_peak[1])
    month_diff_2 = (current_year - second_peak[0]) * 12 + (current_month - second_peak[1])
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


def weekend_holiday_factor(year, month, day, holidays):
    dt = np.array([year, month, day])
    dt = dt.T
    if dt.ndim > 1:
        ts = [date(*x) for x in dt]
    else:
        ts = date(dt[0], dt[1], dt[2])
    is_busday = np.is_busday(ts, holidays=holidays)
    # Non-working days
    # Make customisable when introducing inputs to program
    we_hol_factor = np.where(is_busday, 1, np.random.uniform(0.4, 0.8))
    return we_hol_factor
