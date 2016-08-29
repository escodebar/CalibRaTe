#include <zmq.hpp>

#include <boost/program_options.hpp>

#include <math.h>
#include <string>
#include <iostream>
#include <unistd.h>

#include <TH1F.h>
#include <TH1I.h>
#include <TF1.h>
#include <TSpectrum.h>
#include <TMath.h>
#include "json.hpp"
#include "zhelpers.hpp"

using namespace boost::program_options;
using json = nlohmann::json;

// TODO: Document this program

int main (int ac, char* av[])
{
	std::cout << "Fitter started" << std::endl;
	std::string input  = "tcp://localhost:7000";
	std::string output = "tcp://localhost:8000";

	try {
		options_description desc ("Allowed options");
		desc.add_options()
		("help,h",    "produce help message")
		("input,i",   value (&input),  "Input socket.  Ex: \"tcp://localhost:7000\"")
		("output,o",  value (&output), "Output socket. Ex: \"tcp://localhost:8000\"")
		;

		variables_map vm;
		store (parse_command_line (ac, av, desc), vm);
		notify (vm);

		if (vm.count ("help")) {
			std::cout << desc << std::endl;
			return 0;
		}
	}
	catch (zmq::error_t& e) {
		std::cerr << "zmqerror: " << std::endl;
		return 1;
	}
	catch (std::exception& e) {
		std::cerr << "error: " << e.what() << std::endl;
		return 1;
	}

	// set zmq parameters
	zmq::context_t context (1);
	zmq::socket_t source(context, ZMQ_PULL);
	zmq::socket_t sink(context, ZMQ_PUSH);
	source.connect (input.c_str());
	sink.connect (output.c_str());

	while (true) {

		// The request is json encoded
		std::string message = s_recv (source);
		auto parsed = json::parse(message);

		auto key = parsed["key"];
		auto spectrum = parsed["spectrum"];

		// Create and fill the histogram with the values of the request
		TH1I * hist = new TH1I("", "", 4096, 0, 4095);
		
		int x_min = 4096;
		int x_max = 0;
		
		for (json::iterator it = spectrum.begin(); it != spectrum.end(); ++it) {
			int bin = stoi(it.key());
			double value = it.value();
			hist->SetBinContent(bin, value);
			if (bin < x_min) {
				x_min = bin;
			}
			if (bin > x_max) {
				x_max = bin;
			}
		}

		// Variables needed during iteration
		double * pos;  // number of positions found
		json result;

		// Search for peaks with increasing width.
		// As soon as 5 to 9 of peaks are found their the positions 
		// are determined. Using the latter we estimate the gain by
		// making a linear fit, determining it's chi2 and ndf (number
		// of degrees of freedom). If chi2/ndf is smaller than 5,
		// the positions of the peaks are further examined 
		double threshold = 0.05;
		int peak_width = 1;
		int bin_size = 1;
		do {
			do {
				TH1I * hist2;
				if (bin_size == 1) {
					hist2 = (TH1I *) hist->Clone("newh");
				}
				else {
					hist2 = (TH1I *) hist->Rebin(bin_size, "newh");
				}

				do {
					// A TSpectrum for 10 peaks is needed (10 is about the maximum we
					// will find in the background radiation after only a few thousands
					// events.
					TSpectrum * spectrum = new TSpectrum(10, 1.0);
					int nr_pos = spectrum->Search(hist2, peak_width, "nobackground new", threshold);
				
	
					// If the number of found peaks is in within the range
					if (4 < nr_pos && nr_pos < 10) {
						pos = spectrum->GetPositionX();
						std::sort(pos, pos + nr_pos);

						std::vector<int> positions;

						json j;
						j["threshold"] = threshold;
						j["peak_width"] = peak_width;
						j["bin_size"] = bin_size;

						int good_peaks = 0;
						for (int i = 0; i < nr_pos; ++i) {

							// Fit the gaussian in the histogram at the given position
							int min = (int) (pos[i] - 3*peak_width);
							int max = (int) (pos[i] + 3*peak_width);
							hist2->Fit("gaus", "WQ", "", min, max);
							TF1 * fit = hist2->GetFunction("gaus");
							
							// Get the position and width of the peaks and their uncertainties
							double f_pos = fit->GetParameter(1);
							double f_sig = fit->GetParameter(2);

							double sig_pos = fit->GetParError(1);
							double sig_sig = fit->GetParError(2);

							double chi2 = fit->GetChisquare();
							double ndf = fit->GetNDF();

							if (sig_pos / f_pos < 0.1 && f_pos > x_min && f_pos < x_max) {
								j["fits"].push_back({f_pos, sig_pos});
								++good_peaks;
							}
						}

						if (good_peaks > 4) {
							result["peaks"].push_back(j);
						}

					}
					++peak_width;

				} while (peak_width < 50);

				++bin_size;
			} while (bin_size < 20);
			threshold += 0.02;
		} while (threshold < 0.8);

		// if "peaks" not in json object, then no distances and no gain can be computed
		// push an "ERR" message in that case
		if (result.empty()) {
			s_send (sink, "ERR");
			continue;
		}
		else {
			std::cout << result << std::endl;
		}

		// Now that we found all the peaks for all the parameters,
		// let's calculate the distances and add these to a histogram
		// since the distance between two of our peaks will be the most occurent one,
		// and therefore the gain will be easy to fit.

		TH1I * hist3 = new TH1I("", "", 4096, 0, 4095);
		for (int i = 0; i < result["peaks"].size(); ++i) {
			auto res = result["peaks"].at(i);
			for (int j = 0; j < res["fits"].size(); ++j) {
				for (int k = j+1; k < res["fits"].size(); ++k) {

					// Compute the distance and its uncertainty
					float distance = ((float) res["fits"].at(k)[0] - (float) res["fits"].at(j)[0]);
					float uncertainty = sqrt(pow(
						(float)res["fits"].at(k)[1], 2.0
					) + pow(

						(float)res["fits"].at(j)[1], 2.0
					));

					// Store the distance in the results
					result["distances"].push_back({distance, uncertainty});

					// Add the distance to the histogram
					hist3->Fill(distance, uncertainty);
				}
			}

		}

		// fit a gaussian around the max bin
		int max = hist3->GetMaximumBin();
		hist3->Fit("gaus", "WQ", "", max/2, 3*max/2);
		TF1 * fit2 = hist3->GetFunction("gaus");
							
		// Get the position and width of the peaks and their uncertainties
		result["gain"] = {fit2->GetParameter(1), fit2->GetParameter(2), fit2->GetChisquare(), fit2->GetNDF()};

		// send the request key back with the response
		result["key"] = key;

		// Send results if found any
		s_send (sink, result.dump());
	}

	return 0;
}
