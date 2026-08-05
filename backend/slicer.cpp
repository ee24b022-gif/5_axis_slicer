#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <cstring>
#include <cmath>
#include <algorithm>
#include <iomanip>
#include <sstream>
#include <limits>

using namespace std;

struct Vec3 {
    double x, y, z;
    Vec3() : x(0), y(0), z(0) {}
    Vec3(double x, double y, double z) : x(x), y(y), z(z) {}
    Vec3 operator-(const Vec3& o) const { return Vec3(x - o.x, y - o.y, z - o.z); }
    Vec3 operator+(const Vec3& o) const { return Vec3(x + o.x, y + o.y, z + o.z); }
    Vec3 cross(const Vec3& o) const {
        return Vec3(y * o.z - z * o.y, z * o.x - x * o.z, x * o.y - y * o.x);
    }
    double dot(const Vec3& o) const { return x * o.x + y * o.y + z * o.z; }
    void normalize() {
        double len = sqrt(x*x + y*y + z*z);
        if (len > 0) { x /= len; y /= len; z /= len; }
    }
};

struct Triangle {
    Vec3 v0, v1, v2, normal;
};

// Möller-Trumbore ray-triangle intersection (Ray direction is strictly [0, 0, -1])
bool intersectRayTriangle(const Vec3& orig, const Triangle& tri, double& t) {
    Vec3 dir(0.0, 0.0, -1.0);
    Vec3 edge1 = tri.v1 - tri.v0;
    Vec3 edge2 = tri.v2 - tri.v0;
    Vec3 pvec = dir.cross(edge2);
    double det = edge1.dot(pvec);
    
    if (det > -1e-8 && det < 1e-8) return false;
    double invDet = 1.0 / det;
    
    Vec3 tvec = orig - tri.v0;
    double u = tvec.dot(pvec) * invDet;
    if (u < 0.0 || u > 1.0) return false;
    
    Vec3 qvec = tvec.cross(edge1);
    double v = dir.dot(qvec) * invDet;
    if (v < 0.0 || u + v > 1.0) return false;
    
    t = edge2.dot(qvec) * invDet;
    return t > 1e-8; // Ray intersection must be positive
}

// Read STL (Binary and ASCII) and Center
bool loadSTL(const string& filename, vector<Triangle>& triangles, Vec3& minB, Vec3& maxB) {
    ifstream file(filename, ios::binary | ios::ate);
    if (!file) return false;
    streamsize size = file.tellg();
    file.seekg(0, ios::beg);
    
    if (size < 84) return false; // Too small to be a valid STL
    
    char header[200] = {0};
    file.read(header, min((streamsize)200, size));
    file.seekg(0, ios::beg);
    
    bool isAscii = false;
    for (int i = 0; i < 180; i++) {
        if (strncmp(header + i, "facet normal", 12) == 0) {
            isAscii = true;
            break;
        }
    }
    
    triangles.clear();
    minB = Vec3(1e9, 1e9, 1e9);
    maxB = Vec3(-1e9, -1e9, -1e9);
    
    if (!isAscii) {
        file.seekg(80, ios::beg);
        uint32_t numTriangles = 0;
        file.read(reinterpret_cast<char*>(&numTriangles), 4);
        
        if (84 + numTriangles * 50 > size) {
            return false; // Corrupted binary STL
        }
        
        triangles.reserve(numTriangles);
        for (uint32_t i = 0; i < numTriangles; ++i) {
            float normal[3], v[3][3];
            uint16_t attr;
            file.read(reinterpret_cast<char*>(normal), 12);
            file.read(reinterpret_cast<char*>(v[0]), 12);
            file.read(reinterpret_cast<char*>(v[1]), 12);
            file.read(reinterpret_cast<char*>(v[2]), 12);
            file.read(reinterpret_cast<char*>(&attr), 2);
            
            Triangle tri;
            tri.normal = Vec3(normal[0], normal[1], normal[2]);
            tri.v0 = Vec3(v[0][0], v[0][1], v[0][2]);
            tri.v1 = Vec3(v[1][0], v[1][1], v[1][2]);
            tri.v2 = Vec3(v[2][0], v[2][1], v[2][2]);
            if (tri.normal.dot(tri.normal) < 0.01) {
                tri.normal = (tri.v1 - tri.v0).cross(tri.v2 - tri.v0);
                tri.normal.normalize();
            }
            triangles.push_back(tri);
        }
    } else {
        // Fallback to basic ASCII parse
        file.seekg(0, ios::beg);
        string word;
        Triangle tri;
        int vertexCount = 0;
        while (file >> word) {
            if (word == "facet") {
                file >> word; // normal
                file >> tri.normal.x >> tri.normal.y >> tri.normal.z;
                vertexCount = 0;
            } else if (word == "vertex") {
                if (vertexCount == 0) file >> tri.v0.x >> tri.v0.y >> tri.v0.z;
                else if (vertexCount == 1) file >> tri.v1.x >> tri.v1.y >> tri.v1.z;
                else if (vertexCount == 2) {
                    file >> tri.v2.x >> tri.v2.y >> tri.v2.z;
                    if (tri.normal.dot(tri.normal) < 0.01) {
                        tri.normal = (tri.v1 - tri.v0).cross(tri.v2 - tri.v0);
                        tri.normal.normalize();
                    }
                    triangles.push_back(tri);
                }
                vertexCount++;
            }
        }
    }
    
    if (triangles.empty()) return false;
    
    // Find bounds
    for (const auto& tri : triangles) {
        minB.x = min({minB.x, tri.v0.x, tri.v1.x, tri.v2.x});
        minB.y = min({minB.y, tri.v0.y, tri.v1.y, tri.v2.y});
        minB.z = min({minB.z, tri.v0.z, tri.v1.z, tri.v2.z});
        maxB.x = max({maxB.x, tri.v0.x, tri.v1.x, tri.v2.x});
        maxB.y = max({maxB.y, tri.v0.y, tri.v1.y, tri.v2.y});
        maxB.z = max({maxB.z, tri.v0.z, tri.v1.z, tri.v2.z});
    }
    
    // Center mesh
    double cx = (minB.x + maxB.x) / 2.0;
    double cy = (minB.y + maxB.y) / 2.0;
    double cz = minB.z;
    
    minB = Vec3(1e9, 1e9, 1e9);
    maxB = Vec3(-1e9, -1e9, -1e9);
    
    for (auto& tri : triangles) {
        tri.v0.x -= cx; tri.v0.y -= cy; tri.v0.z -= cz;
        tri.v1.x -= cx; tri.v1.y -= cy; tri.v1.z -= cz;
        tri.v2.x -= cx; tri.v2.y -= cy; tri.v2.z -= cz;
        
        minB.x = min({minB.x, tri.v0.x, tri.v1.x, tri.v2.x});
        minB.y = min({minB.y, tri.v0.y, tri.v1.y, tri.v2.y});
        minB.z = min({minB.z, tri.v0.z, tri.v1.z, tri.v2.z});
        maxB.x = max({maxB.x, tri.v0.x, tri.v1.x, tri.v2.x});
        maxB.y = max({maxB.y, tri.v0.y, tri.v1.y, tri.v2.y});
        maxB.z = max({maxB.z, tri.v0.z, tri.v1.z, tri.v2.z});
    }
    
    return true;
}

struct Point {
    double x, y, z, nx, ny, nz;
};

// Escape JSON strings
string escapeJSON(const string& s) {
    string o;
    for (char c : s) {
        if (c == '"') o += "\\\"";
        else if (c == '\\') o += "\\\\";
        else if (c == '\b') o += "\\b";
        else if (c == '\f') o += "\\f";
        else if (c == '\n') o += "\\n";
        else if (c == '\r') o += "\\r";
        else if (c == '\t') o += "\\t";
        else o += c;
    }
    return o;
}

int main(int argc, char** argv) {
    if (argc < 5) {
        cerr << "Usage: ./slicer_engine <file> <line_width> <y_step> <bed_center_z>\n";
        return 1;
    }
    
    string filename = argv[1];
    double line_width = stod(argv[2]);
    double y_step = stod(argv[3]);
    double bed_center_z = stod(argv[4]);
    
    vector<Triangle> triangles;
    Vec3 minB, maxB;
    if (!loadSTL(filename, triangles, minB, maxB)) {
        cerr << "Failed to load STL\n";
        return 1;
    }
    
    // 2D Spatial Grid for fast Z-raycasting
    // Limit grid to max 500x500 to prevent RAM explosion on scaled STLs
    double cellSize = max(2.0, max(maxB.x - minB.x, maxB.y - minB.y) / 500.0);
    int gridW = ceil((maxB.x - minB.x) / cellSize) + 1;
    int gridH = ceil((maxB.y - minB.y) / cellSize) + 1;
    vector<vector<int>> grid(gridW * gridH);
    
    for (int i = 0; i < triangles.size(); ++i) {
        const auto& tri = triangles[i];
        int minX = max(0, (int)floor((min({tri.v0.x, tri.v1.x, tri.v2.x}) - minB.x) / cellSize));
        int maxX = min(gridW - 1, (int)floor((max({tri.v0.x, tri.v1.x, tri.v2.x}) - minB.x) / cellSize));
        int minY = max(0, (int)floor((min({tri.v0.y, tri.v1.y, tri.v2.y}) - minB.y) / cellSize));
        int maxY = min(gridH - 1, (int)floor((max({tri.v0.y, tri.v1.y, tri.v2.y}) - minB.y) / cellSize));
        
        for (int x = minX; x <= maxX; ++x) {
            for (int y = minY; y <= maxY; ++y) {
                grid[y * gridW + x].push_back(i);
            }
        }
    }
    
    double zStart = maxB.z + 10.0;
    vector<Point> path;
    
    int lineIdx = 0;
    for (double x = minB.x; x <= maxB.x; x += line_width) {
        vector<double> y_pts;
        for (double y = minB.y; y <= maxB.y; y += y_step) y_pts.push_back(y);
        if (lineIdx % 2 != 0) reverse(y_pts.begin(), y_pts.end());
        
        for (double y : y_pts) {
            Vec3 orig(x, y, zStart);
            int gx = max(0, min(gridW - 1, (int)floor((x - minB.x) / cellSize)));
            int gy = max(0, min(gridH - 1, (int)floor((y - minB.y) / cellSize)));
            
            double bestZ = -1e9;
            Vec3 bestNormal(0,0,1);
            bool hit = false;
            
            for (int idx : grid[gy * gridW + gx]) {
                double t;
                if (intersectRayTriangle(orig, triangles[idx], t)) {
                    double hitZ = zStart - t;
                    if (hitZ > bestZ) {
                        bestZ = hitZ;
                        bestNormal = triangles[idx].normal;
                        hit = true;
                    }
                }
            }
            if (hit) {
                path.push_back({x, y, bestZ, bestNormal.x, bestNormal.y, bestNormal.z});
            }
        }
        lineIdx++;
    }
    
    if (path.empty()) {
        cout << "{\"error\": \"No path generated\"}\n";
        return 0;
    }
    
    // Generate G-code & Inverse Kinematics
    ostringstream gcode;
    gcode << "; Open5x Conformal Slicer Output (C++ Engine)\n";
    gcode << "G21 ; Set units to millimeters\n";
    gcode << "G90 ; Absolute positioning\n";
    gcode << "M82 ; Absolute extrusion mode\n";
    gcode << "G28 ; Home all axes\n";
    gcode << "G0 Z50 F3000 ; Move up to avoid collisions\n";
    
    double current_v = 0.0;
    double current_e = 0.0;
    double base_feedrate = 1500.0;
    double e_multiplier = 0.05;
    
    struct State { double mx, my, mz, mu, mv, px, py, pz; };
    State last = {0,0,0,0,0,0,0,0};
    bool first = true;
    
    ostringstream points_json;
    points_json << "[";
    
    for (size_t i = 0; i < path.size(); ++i) {
        const auto& pt = path[i];
        
        points_json << fixed << setprecision(2) << "{\"x\":" << pt.x << ",\"y\":" << pt.y << ",\"z\":" << pt.z << "}";
        if (i < path.size() - 1) points_json << ",";
        
        // Inverse Kinematics
        double v_rad = atan2(pt.nx, pt.ny);
        double xy_mag = sqrt(pt.nx*pt.nx + pt.ny*pt.ny);
        double u_rad = atan2(xy_mag, pt.nz);
        
        Vec3 p(pt.x, pt.y, pt.z + bed_center_z);
        double cv = cos(v_rad), sv = sin(v_rad);
        double cu = cos(u_rad), su = sin(u_rad);
        
        double p_rot_x = cv * p.x - sv * p.y;
        double p_rot_y = cu * (sv * p.x + cv * p.y) - su * p.z;
        double p_rot_z = su * (sv * p.x + cv * p.y) + cu * p.z;
        
        double mx = p_rot_x;
        double my = p_rot_y;
        double mz = p_rot_z - bed_center_z;
        
        double u_deg = u_rad * 180.0 / M_PI;
        double v_deg = v_rad * 180.0 / M_PI;
        
        // Optimize V rotation
        double current_mod = fmod(current_v, 360.0);
        if (current_mod < 0) current_mod += 360.0;
        double target_mod = fmod(v_deg, 360.0);
        if (target_mod < 0) target_mod += 360.0;
        
        double diff = target_mod - current_mod;
        if (diff > 180.0) diff -= 360.0;
        else if (diff < -180.0) diff += 360.0;
        
        current_v += diff;
        double mv = current_v;
        double mu = u_deg;
        
        if (first) {
            gcode << fixed << setprecision(3) << "G0 X" << mx << " Y" << my << " Z" << mz << " U" << mu << " V" << mv << " F3000\n";
            last = {mx, my, mz, mu, mv, pt.x, pt.y, pt.z};
            first = false;
            continue;
        }
        
        double dist_part = sqrt(pow(pt.x - last.px, 2) + pow(pt.y - last.py, 2) + pow(pt.z - last.pz, 2));
        double dist_mach = sqrt(pow(mx - last.mx, 2) + pow(my - last.my, 2) + pow(mz - last.mz, 2) + pow(mu - last.mu, 2) + pow(mv - last.mv, 2));
        
        current_e += dist_part * e_multiplier;
        double feedrate = (dist_part > 0) ? (base_feedrate * (dist_mach / dist_part)) : base_feedrate;
        if (feedrate > 6000.0) feedrate = 6000.0;
        
        gcode << fixed << setprecision(3) << "G1 X" << mx << " Y" << my << " Z" << mz << " U" << mu << " V" << mv << " E" << current_e << " F" << setprecision(1) << feedrate << "\n";
        last = {mx, my, mz, mu, mv, pt.x, pt.y, pt.z};
    }
    points_json << "]";
    
    // Output JSON
    cout << "{\"toolpath_points\":" << points_json.str() << ",\"gcode\":\"" << escapeJSON(gcode.str()) << "\"}\n";
    return 0;
}
