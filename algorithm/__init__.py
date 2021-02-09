from max30102 import MAX30102
from time import time
from math import pow, sqrt
import numpy as np


class Rf_Algorithm():
    def __init__(self):
        self.ST = 4
        self.FS = 25

        self.MAX_HR = 200
        self.MIN_HR = 40

        self.min_autocorrelation_ratio = 0.4
        self.min_pearson_correlation = 0.6

        self.BUFFER_SIZE = self.ST*self.FS
        self.FS60 = self.FS*60
        self.LOWEST_PERIOD = int(self.FS60/self.MAX_HR)
        self.HIGHEST_PERIOD = int(self.FS60/self.MIN_HR)

        self.mean_X = (self.BUFFER_SIZE-1)/2
        self.sum_X2 = 83325
        self.n_last_peak_interval = self.LOWEST_PERIOD

    def heart_rate_and_oxygen_saturation(self, pun_ir_buffer, pun_red_buffer):
        f_ir_mean = 0.0
        f_red_mean = 0.0
        f_ir_sumsq = 0.0
        f_red_sumsq = 0.0
        f_y_ac = 0.0
        f_x_ac = 0.0
        xy_ratio = 0.0
        beta_ir = 0.0
        beta_red = 0.0
        an_x = []  # ir
        an_y = []  # red

        # calculates DC mean and subtracts DC from ir and red
        f_ir_mean = 0.0
        f_red_mean = 0.0
        for k in range(self.BUFFER_SIZE):
            f_ir_mean += pun_ir_buffer[k]
            f_red_mean += pun_red_buffer[k]
        f_ir_mean = f_ir_mean/self.BUFFER_SIZE
        f_red_mean = f_red_mean/self.BUFFER_SIZE
        # remove DC
        an_x = [pun_ir_buffer[k] -
                f_ir_mean for k in range(self.BUFFER_SIZE)]
        an_y = [pun_red_buffer[k] -
                f_red_mean for k in range(self.BUFFER_SIZE)]

        # RF, remove linear trend (baseline leveling)
        beta_ir = self.rf_linear_regression_beta(
            an_x, self.mean_X, self.sum_X2)
        beta_red = self.rf_linear_regression_beta(
            an_y, self.mean_X, self.sum_X2)

        an_x = [an_x[(k)] - beta_ir *
                (k-self.mean_X) for k in range(self.BUFFER_SIZE)]
        an_y = [an_y[(k)] - beta_red *
                (k-self.mean_X) for k in range(self.BUFFER_SIZE)]

        # For SpO2 calculate RMS of both AC signals. In addition, pulse detector needs raw sum of squares for IR
        f_y_ac = self.rf_rms(an_y)
        f_red_sumsq = pow(f_y_ac, 2)
        f_x_ac = self.rf_rms(an_x)
        f_ir_sumsq = pow(f_x_ac, 2)
        # Calculate Pearson correlation between red and IR
        correl = self.rf_Pcorrelation(
            an_x, an_y)/sqrt(f_red_sumsq*f_ir_sumsq)
        # find signal periodicity
        if correl >= self.min_pearson_correlation:
            if self.LOWEST_PERIOD == self.n_last_peak_interval:
                self.n_last_peak_interval = self.rf_initialize_periodicity_search(
                    an_x, self.n_last_peak_interval, f_ir_sumsq)

            if self.n_last_peak_interval != 0:
                self.n_last_peak_interval = self.rf_signal_periodicity(an_x, self.n_last_peak_interval, self.LOWEST_PERIOD,
                                                                       self.HIGHEST_PERIOD, self.min_autocorrelation_ratio, f_ir_sumsq)
        else:
            self.n_last_peak_interval = 0

        # Calculate heart rate if periodicity detector was successful. Otherwise, reset peak interval to its initial value and report error.
        pn_heart_rate = -999
        pch_hr_valid = False
        pn_spo2 = -999
        pch_spo2_valid = False
        if self.n_last_peak_interval != 0:
            pn_heart_rate = (self.FS60/self.n_last_peak_interval)
            pch_hr_valid = True
        else:  # unable to calculate because signal looks aperiodic, do not use SpO2 value from this corrupt signal
            self.n_last_peak_interval = self.LOWEST_PERIOD
            return (pn_heart_rate, pch_hr_valid, pn_spo2, pch_spo2_valid)

        # After trend removal, the mean represents DC level
        # formula is (f_y_ac*f_x_dc) / (f_x_ac*f_y_dc)
        xy_ratio = (f_y_ac*f_ir_mean)/(f_x_ac*f_red_mean)
        if xy_ratio > 0.02 and xy_ratio < 1.84:  # Check boundaries of applicability
            pn_spo2 = (-45.060*xy_ratio + 30.354)*xy_ratio + 93.645
            pch_spo2_valid = True
        else:
            pn_spo2 = -999
            pch_spo2_valid = False

        return (int(pn_heart_rate), pch_hr_valid, pn_spo2, pch_spo2_valid)

    def rf_initialize_periodicity_search(self, pn_x, p_last_periodicity, aut_lag0):
        aut = 0.0
        aut_right = 0.0
        n_lag = p_last_periodicity
        aut_right = aut = self.rf_autocorrelation(
            pn_x, n_lag)
        if aut/aut_lag0 >= self.min_autocorrelation_ratio:
            aut = aut_right
            n_lag += 2
            aut_right = self.rf_autocorrelation(pn_x, n_lag)
            while aut_right/aut_lag0 >= self.min_autocorrelation_ratio and aut_right < aut and n_lag <= self.HIGHEST_PERIOD:
                aut = aut_right
                n_lag += 2
                aut_right = self.rf_autocorrelation(
                    pn_x,  n_lag)
            if n_lag > self.HIGHEST_PERIOD:
                p_last_periodicity = 0
                return p_last_periodicity

            aut = aut_right

        aut = aut_right
        n_lag += 2
        aut_right = self.rf_autocorrelation(pn_x,  n_lag)
        while aut_right/aut_lag0 < self.min_autocorrelation_ratio and n_lag <= self.HIGHEST_PERIOD:
            aut = aut_right
            n_lag += 2
            aut_right = self.rf_autocorrelation(pn_x, n_lag)
        if n_lag > self.HIGHEST_PERIOD:
            p_last_periodicity = 0
        else:
            p_last_periodicity = n_lag
        return p_last_periodicity

    def rf_signal_periodicity(self, pn_x, p_last_periodicity, n_min_distance,  n_max_distance,  min_aut_ratio, aut_lag0):
        n_lag = 0
        aut = 0.0
        aut_left = 0.0
        aut_right = 0.0
        aut_save = 0.0
        left_limit_reached = False

        n_lag = p_last_periodicity
        aut_save = aut = self.rf_autocorrelation(pn_x, n_lag)

        aut_left = aut
        while (aut_left > aut) and (n_lag >= n_min_distance):
            aut = aut_left
            n_lag -= 1
            aut_left = self.rf_autocorrelation(pn_x, n_lag)
            if (aut_left > aut) and (n_lag >= n_min_distance):
                break

        if n_lag < n_min_distance:
            left_limit_reached = True
            n_lag = p_last_periodicity
            aut = aut_save
        else:
            n_lag += 1

        if n_lag == p_last_periodicity:
            aut_right = aut
            while aut_right > aut and n_lag <= n_max_distance:
                aut = aut_right
                n_lag += 1
                aut_right = self.rf_autocorrelation(
                    pn_x, n_lag)
                if aut_right > aut and n_lag <= n_max_distance:
                    break

            if n_lag > n_max_distance:
                n_lag = 0
            else:
                n_lag -= 1

            if n_lag == p_last_periodicity and left_limit_reached:
                n_lag = 0
        ratio = aut/aut_lag0
        if ratio < min_aut_ratio:
            n_lag = 0
        p_last_periodicity = n_lag
        return p_last_periodicity

    @staticmethod
    def rf_linear_regression_beta(pn_x, xmean, sum_x2):
        rng = np.arange(-xmean, xmean+1, 1)
        beta = 0.0
        for i in range(len(rng)):
            x = rng[i]
            beta += x*pn_x[i]
        return beta/sum_x2

    def rf_autocorrelation(self, pn_x, n_lag):
        n_temp = self.BUFFER_SIZE-n_lag
        _sum = 0.0

        if n_temp <= 0:
            return _sum
        for i in range(n_temp):
            pn_ptr = pn_x[i]
            _sum += pn_ptr * pn_x[i+n_lag]
        return _sum/n_temp

    def rf_rms(self, pn_x):
        sumsq = 0.0
        for i in range(self.BUFFER_SIZE):
            pn_ptr = pn_x[i]
            sumsq += pn_ptr * pn_ptr
        sumsq = int(sumsq) / self.BUFFER_SIZE

        return sqrt(sumsq)

    def rf_Pcorrelation(self, pn_x, pn_y):
        x_ptr = 0
        y_ptr = 0
        r = 0.0

        for i in range(self.BUFFER_SIZE):
            x_ptr = pn_x[i]
            y_ptr = pn_y[i]
            r += (x_ptr)*(y_ptr)
        r = r/self.BUFFER_SIZE

        return r
